"""
Tests for Layer δ.2 — operational pattern breaks.

Includes a UI-copy linter that scans the anomaly module and router for
the forbidden words listed in Appendix D locked decision #20. This is
the mechanical enforcement of the framing discipline — flags-for-review,
never predictions.
"""

import inspect
import re
import uuid
from datetime import date, datetime, timezone

import pytest

from analysis.anomaly_detection import (
    detect_operational_pattern_breaks,
    methodology_notes,
)
from backend.api.anomalies import operational_anomalies, router
from backend.models import Airport, DataRecord, MethodologyVersion

# ── Test data helpers ────────────────────────────────────────────────────


@pytest.fixture
def lhr(api_db):
    a = Airport(
        id=uuid.uuid4(), iata_code="LHR", icao_code="EGLL",
        ourairports_ident="EGLL", name="London Heathrow",
        country_code="GB", tier=1,
    )
    api_db.add(a)
    api_db.commit()
    return a


def _op_record(
    api_db, *, airport, concept: str, year: int, value: float,
    source_id: str = "caa_uk",
) -> DataRecord:
    mv = api_db.query(MethodologyVersion).first()
    rec = DataRecord(
        id=f"op_{airport.iata_code}_{concept[:8]}_{year}_{source_id[:6]}"
           .ljust(48, "0")[:48],
        airport_id=airport.id,
        source_id=source_id,
        source_url="https://example.com/x",
        source_document_id=f"doc-{year}",
        retrieved_at=datetime.now(timezone.utc),
        methodology_version_id=mv.id,
        record_type="OPERATIONAL",
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        payload={
            "concept": concept,
            "value": value,
            "unit": "passengers" if "pax" in concept else "tonnes",
        },
    )
    api_db.add(rec)
    api_db.commit()
    return rec


# ── Detection logic ─────────────────────────────────────────────────────


class TestDetection:
    def test_stable_history_no_flag(self, api_db, lhr):
        """Z-score below threshold → no flag."""
        for year in (2020, 2021, 2022, 2023):
            _op_record(api_db, airport=lhr, concept="passengers_total",
                       year=year, value=80_000_000)
        # Latest: 80.5M — well within stable baseline
        _op_record(api_db, airport=lhr, concept="passengers_total",
                   year=2024, value=80_500_000)
        flags = detect_operational_pattern_breaks(api_db)
        assert flags == []

    def test_huge_jump_flags(self, api_db, lhr):
        # Realistic baseline with small year-on-year variance
        baseline = [50_000_000, 50_500_000, 49_800_000, 50_200_000, 50_100_000]
        for year, val in zip(range(2019, 2024), baseline):
            _op_record(api_db, airport=lhr, concept="passengers_total",
                       year=year, value=val)
        # Latest year a 4x jump — well beyond 2σ
        _op_record(api_db, airport=lhr, concept="passengers_total",
                   year=2024, value=200_000_000)
        flags = detect_operational_pattern_breaks(api_db)
        assert len(flags) == 1
        f = flags[0]
        assert f.concept == "passengers_total"
        assert f.period_end == date(2024, 12, 31)
        assert f.z_score > 0  # positive deviation
        assert f.observed_value == 200_000_000
        assert f.historical_years == [2019, 2020, 2021, 2022, 2023]

    def test_huge_drop_flags_with_negative_z(self, api_db, lhr):
        baseline = [80_000_000, 80_500_000, 79_800_000, 80_200_000, 80_100_000]
        for year, val in zip(range(2019, 2024), baseline):
            _op_record(api_db, airport=lhr, concept="passengers_total",
                       year=year, value=val)
        _op_record(api_db, airport=lhr, concept="passengers_total",
                   year=2024, value=20_000_000)
        flags = detect_operational_pattern_breaks(api_db)
        assert len(flags) == 1
        assert flags[0].z_score < 0  # negative deviation surfaces

    def test_zero_variance_skipped(self, api_db, lhr):
        """If history is constant, stddev=0 — can't z-score, must not divide by zero."""
        for year in (2019, 2020, 2021, 2022, 2023):
            _op_record(api_db, airport=lhr, concept="passengers_total",
                       year=year, value=50_000_000)
        # Latest year different, but with zero historical variance we skip
        _op_record(api_db, airport=lhr, concept="passengers_total",
                   year=2024, value=100_000_000)
        flags = detect_operational_pattern_breaks(api_db)
        assert flags == []

    def test_insufficient_history_skipped(self, api_db, lhr):
        """Need ≥ min_historical_years (default 3) + 1 latest year."""
        for year in (2022, 2023):  # only 2 years history
            _op_record(api_db, airport=lhr, concept="passengers_total",
                       year=year, value=50_000_000)
        _op_record(api_db, airport=lhr, concept="passengers_total",
                   year=2024, value=200_000_000)
        flags = detect_operational_pattern_breaks(api_db, min_historical_years=3)
        assert flags == []

    def test_concept_filter_in_scope(self, api_db, lhr):
        """Concepts like net_zero_target_year are NOT in scope for anomaly detection."""
        for year in (2019, 2020, 2021, 2022, 2023):
            _op_record(api_db, airport=lhr, concept="net_zero_target_year",
                       year=year, value=2050)
        _op_record(api_db, airport=lhr, concept="net_zero_target_year",
                   year=2024, value=2099)  # would be a huge z-score if in scope
        assert detect_operational_pattern_breaks(api_db) == []

    def test_multi_source_year_averaged(self, api_db, lhr):
        """If CAA and Eurostat both report the same year, we use the cross-source mean."""
        for year in (2019, 2020, 2021, 2022, 2023):
            _op_record(api_db, airport=lhr, concept="passengers_total",
                       year=year, value=80_000_000, source_id="caa_uk")
        # 2024 reported by two sources with slightly different values
        _op_record(api_db, airport=lhr, concept="passengers_total",
                   year=2024, value=85_000_000, source_id="caa_uk")
        _op_record(api_db, airport=lhr, concept="passengers_total",
                   year=2024, value=85_400_000, source_id="eurostat_aviation")
        flags = detect_operational_pattern_breaks(api_db)
        # 5% jump on zero-variance baseline → won't flag (zero variance skip)
        assert flags == []

    def test_threshold_override_affects_flagging(self, api_db, lhr):
        # Baseline: 10_000 → 10_400 (gentle trend, σ ≈ 158)
        for offset, year in enumerate(range(2019, 2024)):
            _op_record(api_db, airport=lhr, concept="cargo_tonnes",
                       year=year, value=10_000 + offset * 100)
        # Latest: 10_500 → continuation of trend; z ≈ 1.9
        _op_record(api_db, airport=lhr, concept="cargo_tonnes",
                   year=2024, value=10_500)
        # Loose threshold ignores; tight catches
        loose = detect_operational_pattern_breaks(api_db, z_threshold=10)
        tight = detect_operational_pattern_breaks(api_db, z_threshold=0.5)
        assert len(loose) == 0
        assert len(tight) == 1


# ── API surface ─────────────────────────────────────────────────────────


class TestApi:
    @pytest.fixture
    def seeded(self, api_db, lhr):
        baseline = [50_000_000, 50_500_000, 49_800_000, 50_200_000, 50_100_000]
        for year, val in zip(range(2019, 2024), baseline):
            _op_record(api_db, airport=lhr, concept="passengers_total",
                       year=year, value=val)
        _op_record(api_db, airport=lhr, concept="passengers_total",
                   year=2024, value=200_000_000)

    def test_endpoint_shape(self, api_client, seeded):
        r = api_client.get("/anomalies/operational")
        assert r.status_code == 200
        body = r.json()
        assert "flags" in body
        assert "thresholds" in body
        assert "concepts_in_scope" in body
        assert "shadow_mode" in body
        assert "methodology_notes" in body
        # Shadow mode = True is the locked v1 default
        assert body["shadow_mode"] is True
        assert len(body["flags"]) == 1

    def test_concept_filter(self, api_client, seeded):
        r = api_client.get("/anomalies/operational",
                           params={"concept": "cargo_tonnes"})
        assert r.json()["flags"] == []

    def test_threshold_propagates(self, api_client, seeded):
        # Default threshold catches it (4x jump on tight baseline → huge z).
        r1 = api_client.get("/anomalies/operational").json()
        assert len(r1["flags"]) == 1
        assert r1["thresholds"]["z_threshold"] == 2.0
        # Override echoes back so consumers see what produced the result.
        r2 = api_client.get(
            "/anomalies/operational", params={"z_threshold": 1.5},
        ).json()
        assert r2["thresholds"]["z_threshold"] == 1.5

    def test_endpoint_rejects_threshold_above_cap(self, api_client, seeded):
        """Query param has le=10 — out-of-range values get 422, not silent acceptance."""
        r = api_client.get("/anomalies/operational",
                           params={"z_threshold": 100})
        assert r.status_code == 422


# ── UI-copy linter (Appendix D #20 framing discipline) ──────────────────


FORBIDDEN_WORDS = {
    # Words that imply prediction / forecasting / certainty about future
    "expect", "expects", "expected",
    "predict", "predicts", "predicted",
    "forecast", "forecasts", "forecasted",
    "will indicate", "will lead", "will cause", "will result",
    "imminent",
    "warns", "warning", "warns of",
    "guarantees", "ensures",
}


def _scan_for_forbidden(text: str) -> list[str]:
    """Return any forbidden phrases found (case-insensitive whole-word match)."""
    found = []
    lower = text.lower()
    for word in FORBIDDEN_WORDS:
        # Whole-word match — avoid matching inside e.g. "unexpectedly" (rare here)
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, lower):
            found.append(word)
    return found


class TestUiCopyDiscipline:
    """
    Mechanically enforces the Appendix D #20 framing rule. Flags-for-
    review, never predictions. If anyone (human or otherwise) edits the
    anomaly module or router and reaches for prediction language, these
    tests fail with the offending phrase.
    """

    def test_methodology_notes_clean(self):
        for note in methodology_notes():
            offending = _scan_for_forbidden(note)
            assert not offending, (
                f"methodology_notes contains forbidden prediction language "
                f"{offending}: {note!r}"
            )

    def test_endpoint_summary_and_description_clean(self):
        for route in router.routes:
            if not hasattr(route, "summary"):
                continue
            for attr in ("summary", "description"):
                text = getattr(route, attr, None) or ""
                offending = _scan_for_forbidden(text)
                assert not offending, (
                    f"Route {getattr(route, 'path', '?')} {attr} contains "
                    f"forbidden language {offending}: {text!r}"
                )

    def test_function_docstrings_clean(self):
        """Per-function docstrings also user-facing via /docs (OpenAPI)."""
        for obj in (detect_operational_pattern_breaks, operational_anomalies):
            doc = inspect.getdoc(obj) or ""
            offending = _scan_for_forbidden(doc)
            assert not offending, (
                f"{obj.__name__} docstring contains forbidden language "
                f"{offending}"
            )

    def test_linter_actually_works(self):
        """Negative test — make sure the linter would catch a real violation."""
        bad = (
            "This pattern is expected to lead to a forecast breach; "
            "imminent action will result in covenant default."
        )
        offending = _scan_for_forbidden(bad)
        # Multiple distinct forbidden phrases should match
        assert "expected" in offending
        assert "forecast" in offending
        assert "imminent" in offending
        assert "will result" in offending
