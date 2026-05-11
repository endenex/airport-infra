"""Tests for analysis.lifecycle_position (Appendix D Layer α)."""

import uuid
from datetime import date, datetime, timezone

import pytest

from analysis.lifecycle_position import (
    LifecycleInputs,
    classify,
    compute_and_persist_all,
    compute_for_airport,
    compute_inputs,
)
from backend.models import Airport, DataRecord, MethodologyVersion


def _make_record(
    api_db, airport_id, concept: str, value: float, period_start: date | None,
    period_end: date, framework: str = "H7", record_type: str = "CONCESSION",
) -> DataRecord:
    mv = api_db.query(MethodologyVersion).first()
    rid = f"rec_{concept[:10]}_{period_end.isoformat()}"
    rid = rid + "0" * (48 - len(rid))
    rec = DataRecord(
        id=rid,
        airport_id=airport_id,
        source_id="caa_h7",
        source_url="https://example.com/h7.pdf",
        source_document_id="doc-h7",
        retrieved_at=datetime.now(timezone.utc),
        methodology_version_id=mv.id,
        record_type=record_type,
        period_start=period_start,
        period_end=period_end,
        payload={
            "concept": concept,
            "value": value,
            "unit": "GBP_million",
            "regulator_name": "UK Civil Aviation Authority",
            "regulatory_framework_name": framework,
        },
    )
    api_db.add(rec)
    return rec


@pytest.fixture
def lhr(api_db):
    a = Airport(
        id=uuid.uuid4(), iata_code="LHR", icao_code="EGLL",
        ourairports_ident="EGLL", name="London Heathrow",
        country_code="GB", tier=1,
    )
    api_db.add(a)
    # Seed methodology version 1.1.0 if absent — preserved across tests
    # because conftest's api_db fixture doesn't truncate methodology_versions.
    if api_db.query(MethodologyVersion).filter_by(version_string="1.1.0").first() is None:
        api_db.add(MethodologyVersion(
            version_string="1.1.0",
            description="Lifecycle Position v1 (test fixture)",
        ))
    api_db.commit()
    return a


@pytest.fixture
def lhr_with_h7(api_db, lhr):
    """LHR seeded with the H7 CONCESSION records (the real H7 figures)."""
    # H7 covers 2022-01-01 → 2026-12-31, total capex £3,620M
    _make_record(api_db, lhr.id, "capex_allowance_total_million", 3620.0,
                 date(2022, 1, 1), date(2026, 12, 31))
    # Annual capex profile
    for year, capex in [(2022, 367), (2023, 567), (2024, 703), (2025, 1017), (2026, 967)]:
        _make_record(api_db, lhr.id, "forecast_capex_million", float(capex),
                     date(year, 1, 1), date(year, 12, 31))
    api_db.commit()
    return lhr


# ── classify() — the rule-by-rule logic ────────────────────────────────


class TestClassify:
    def test_late_when_horizon_below_30(self):
        inputs = LifecycleInputs(
            concession_horizon_remaining_pct=25.0, capex_programme_completion_pct=10.0,
        )
        stage, rationale = classify(inputs)
        assert stage == "late"
        assert "horizon" in rationale.lower()

    def test_late_when_debt_above_70(self):
        inputs = LifecycleInputs(
            concession_horizon_remaining_pct=80.0,
            capex_programme_completion_pct=10.0, debt_amortisation_pct=75.0,
        )
        stage, rationale = classify(inputs)
        assert stage == "late"
        assert "debt" in rationale.lower()

    def test_early_requires_all_three_signals(self):
        inputs = LifecycleInputs(
            capex_programme_completion_pct=20.0,
            debt_amortisation_pct=10.0,
            concession_horizon_remaining_pct=80.0,
        )
        stage, _ = classify(inputs)
        assert stage == "early"

    def test_early_fails_without_debt_input(self):
        """All-three rule means missing debt blocks early classification."""
        inputs = LifecycleInputs(
            capex_programme_completion_pct=20.0,
            debt_amortisation_pct=None,
            concession_horizon_remaining_pct=80.0,
        )
        # capex < 30% but not in [30,70], so falls through to indeterminate
        stage, _ = classify(inputs)
        assert stage == "indeterminate"

    def test_mid_when_capex_in_band(self):
        inputs = LifecycleInputs(
            capex_programme_completion_pct=50.0,
            concession_horizon_remaining_pct=50.0,
        )
        stage, rationale = classify(inputs)
        assert stage == "mid"
        assert "30" in rationale and "70" in rationale

    def test_indeterminate_when_no_inputs(self):
        stage, _ = classify(LifecycleInputs())
        assert stage == "indeterminate"

    def test_late_dominates_capex_signal(self):
        """Horizon < 30% wins even if capex would otherwise indicate mid."""
        inputs = LifecycleInputs(
            concession_horizon_remaining_pct=20.0,
            capex_programme_completion_pct=50.0,  # would be mid on its own
        )
        stage, _ = classify(inputs)
        assert stage == "late"


# ── compute_inputs() — pulling from CONCESSION records ─────────────────


class TestComputeInputs:
    def test_horizon_and_capex_computed_from_h7(self, api_db, lhr_with_h7):
        # Mid-2024: 2.5 years into 5-year period, ~50% horizon remaining
        inputs = compute_inputs(api_db, lhr_with_h7, today=date(2024, 7, 1))
        assert inputs.concession_horizon_remaining_pct is not None
        assert 49 < inputs.concession_horizon_remaining_pct < 52
        # Capex through mid-2024: 367 + 567 + ~half of 703 ≈ 1285 / 3620 ≈ 35%
        assert inputs.capex_programme_completion_pct is not None
        assert 33 < inputs.capex_programme_completion_pct < 38

    def test_no_concession_records_yields_empty_inputs(self, api_db, lhr):
        inputs = compute_inputs(api_db, lhr, today=date(2024, 7, 1))
        assert inputs.concession_horizon_remaining_pct is None
        assert inputs.capex_programme_completion_pct is None
        assert any("no CONCESSION records" in n for n in inputs.methodology_notes)

    def test_methodology_notes_record_regulated_proxy_assumption(self, api_db, lhr_with_h7):
        inputs = compute_inputs(api_db, lhr_with_h7, today=date(2024, 7, 1))
        joined = " ".join(inputs.methodology_notes)
        assert "regulated airport" in joined
        assert "H7" in joined
        assert "forecast" in joined.lower()  # capex caveat
        assert "debt" in joined.lower()      # debt unavailability note

    def test_source_record_ids_populated(self, api_db, lhr_with_h7):
        inputs = compute_inputs(api_db, lhr_with_h7, today=date(2024, 7, 1))
        # 1 total + 5 annual = 6 CONCESSION records contribute
        assert len(inputs.source_record_ids) >= 5


# ── compute_for_airport() — end-to-end classification ───────────────────


class TestComputeForAirport:
    def test_lhr_late_stage_in_mid_2026(self, api_db, lhr_with_h7):
        """May 2026 = ~88% through H7, well into late-stage by horizon."""
        position = compute_for_airport(api_db, lhr_with_h7, today=date(2026, 5, 11))
        assert position.stage == "late"
        assert position.methodology_version == "1.1.0"
        assert "horizon" in position.rationale.lower()
        assert position.inputs.concession_horizon_remaining_pct is not None
        assert position.inputs.concession_horizon_remaining_pct < 30


# ── compute_and_persist_all() — writes onto airport row ─────────────────


class TestPersist:
    def test_persists_stage_and_inputs_onto_airport_row(self, api_db, lhr_with_h7):
        compute_and_persist_all(api_db, iatas=["LHR"], today=date(2026, 5, 11))
        api_db.refresh(lhr_with_h7)
        assert lhr_with_h7.lifecycle_stage == "late"
        assert lhr_with_h7.lifecycle_methodology_version_id is not None
        assert lhr_with_h7.lifecycle_computed_at is not None
        assert lhr_with_h7.lifecycle_inputs is not None
        assert "rationale" in lhr_with_h7.lifecycle_inputs
        assert lhr_with_h7.lifecycle_inputs["concession_horizon_remaining_pct"] is not None

    def test_default_skips_airports_without_concession_data(self, api_db, lhr):
        """An airport with no CONCESSION records should not get classified."""
        summary = compute_and_persist_all(api_db, today=date(2026, 5, 11))
        # lhr has no concession data, so it isn't in the default query
        assert summary["computed"] == 0


# ── API surface ─────────────────────────────────────────────────────────


class TestLifecycleViaApi:
    def test_lifecycle_appears_in_airport_detail(self, api_client, api_db, lhr_with_h7):
        compute_and_persist_all(api_db, iatas=["LHR"], today=date(2026, 5, 11))
        r = api_client.get("/airports/LHR")
        assert r.status_code == 200
        body = r.json()
        assert body["lifecycle"] is not None
        assert body["lifecycle"]["stage"] == "late"
        assert body["lifecycle"]["methodology_version"] == "1.1.0"
        # Inputs blob includes the rationale and the per-signal percentages
        inputs = body["lifecycle"]["inputs"]
        assert "rationale" in inputs
        assert inputs["concession_horizon_remaining_pct"] is not None

    def test_lifecycle_is_null_when_not_computed(self, api_client, api_db, lhr):
        """Airport with no lifecycle computation yet returns null lifecycle."""
        r = api_client.get("/airports/LHR")
        assert r.status_code == 200
        assert r.json()["lifecycle"] is None
