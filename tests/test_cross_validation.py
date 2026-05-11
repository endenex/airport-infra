"""End-to-end tests for analysis.cross_validation."""

import uuid
from datetime import date, datetime, timezone

import pytest

from analysis.cross_validation import cross_validate
from backend.models import Airport, CrossValidation, DataRecord, MethodologyVersion


@pytest.fixture
def cv_db(api_db):
    """Seed two airports + records from CAA, Eurostat and an LLM pipeline."""
    mv = api_db.query(MethodologyVersion).first()
    lhr = Airport(id=uuid.uuid4(), iata_code="LHR", icao_code="EGLL",
                  ourairports_ident="EGLL", name="London Heathrow",
                  country_code="GB", tier=1)
    cdg = Airport(id=uuid.uuid4(), iata_code="CDG", icao_code="LFPG",
                  ourairports_ident="LFPG", name="Paris CDG",
                  country_code="FR", tier=1)
    api_db.add_all([lhr, cdg])
    api_db.flush()

    retrieved = datetime.now(timezone.utc)
    end_2024 = date(2024, 12, 31)

    def _rec(rec_id: str, airport_id, source_id: str, value: float) -> DataRecord:
        return DataRecord(
            id=rec_id + "0" * (48 - len(rec_id)),
            airport_id=airport_id, source_id=source_id,
            source_url="https://example.com/x", source_document_id="doc",
            retrieved_at=retrieved, methodology_version_id=mv.id,
            record_type="OPERATIONAL", period_end=end_2024,
            payload={"concept": "passengers_total", "value": value, "unit": "passengers"},
        )

    # LHR — CAA agrees within 0.05% with LLM; both should be a clean comparison.
    api_db.add(_rec("rec_lhr_caa_", lhr.id, "caa_uk", 83_857_297))
    api_db.add(_rec("rec_lhr_llm_", lhr.id, "llm:operationalextractionpipeline", 83_900_000))
    # CDG — Eurostat alone, no second source → no comparison row.
    api_db.add(_rec("rec_cdg_es_", cdg.id, "eurostat_aviation", 70_257_116))
    api_db.commit()

    return {"lhr": lhr, "cdg": cdg, "mv": mv}


class TestCrossValidate:
    def test_creates_pair_for_lhr_caa_vs_llm(self, api_db, cv_db):
        summary = cross_validate(api_db, concept="passengers_total")
        # LHR has 2 sources → 1 comparison; CDG has 1 source → 0.
        assert summary["pairwise_comparisons"] == 1
        assert summary["agreements"] == 1  # within 2% threshold
        assert summary["flagged_for_review"] == 0
        rows = api_db.query(CrossValidation).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.field_name == "passengers_total"
        # CAA is authoritative → primary
        assert row.primary_value["source_id"] == "caa_uk"
        assert row.comparison_value["source_id"] == "llm:operationalextractionpipeline"
        assert row.agreement is True
        assert abs(row.discrepancy_pct) < 0.1  # ~0.05% in this example

    def test_flags_llm_disagreement_above_threshold(self, api_db, cv_db):
        # Replace the LLM record with one that's 10% off CAA
        rec = api_db.query(DataRecord).filter(
            DataRecord.source_id == "llm:operationalextractionpipeline"
        ).one()
        rec.payload = {**rec.payload, "value": 92_242_500}  # +10% vs CAA 83.86M
        api_db.commit()

        cross_validate(api_db, concept="passengers_total")
        rows = api_db.query(CrossValidation).all()
        assert len(rows) == 1
        assert rows[0].agreement is False
        assert rows[0].flagged_for_review is True

    def test_does_not_flag_structured_source_disagreement(self, api_db, cv_db):
        """CAA vs Eurostat at 10% should NOT auto-flag — methodology difference."""
        mv = cv_db["mv"]
        # Add a Eurostat record for LHR (pre-Brexit data scenario), 10% lower than CAA
        api_db.add(DataRecord(
            id="rec_lhr_es_" + "0" * 37, airport_id=cv_db["lhr"].id,
            source_id="eurostat_aviation",
            source_url="x", source_document_id="es",
            retrieved_at=datetime.now(timezone.utc), methodology_version_id=mv.id,
            record_type="OPERATIONAL", period_end=date(2024, 12, 31),
            payload={"concept": "passengers_total", "value": 75_471_567, "unit": "passengers"},
        ))
        api_db.commit()
        summary = cross_validate(api_db, concept="passengers_total")
        # LHR now has 3 sources → C(3,2)=3 pairs
        assert summary["pairwise_comparisons"] == 3
        caa_es = next(r for r in api_db.query(CrossValidation).all()
                      if r.primary_value["source_id"] == "caa_uk"
                      and r.comparison_value["source_id"] == "eurostat_aviation")
        assert caa_es.agreement is False  # 10% disagreement
        assert caa_es.flagged_for_review is False  # but no LLM involved → not flagged

    def test_skips_within_source_pairs(self, api_db, cv_db):
        """Two Eurostat records for same airport (e.g. FR_LFSB + CH_LFSB) shouldn't pair."""
        mv = cv_db["mv"]
        # Two Eurostat records for CDG (different eurostat codes, same airport_id)
        api_db.add(DataRecord(
            id="rec_cdg_es_2" + "0" * 36, airport_id=cv_db["cdg"].id,
            source_id="eurostat_aviation",
            source_url="x", source_document_id="es-2",
            retrieved_at=datetime.now(timezone.utc), methodology_version_id=mv.id,
            record_type="OPERATIONAL", period_end=date(2024, 12, 31),
            payload={"concept": "passengers_total", "value": 1_000_000, "unit": "passengers"},
        ))
        api_db.commit()
        summary = cross_validate(api_db, concept="passengers_total")
        # CDG now has 2 records but same source → 0 comparisons added for CDG
        # LHR still gives its 1 comparison.
        assert summary["pairwise_comparisons"] == 1


class TestCrossValidationApi:
    def test_list_endpoint(self, api_client, api_db, cv_db):
        """/cross-validations surfaces the rows that cross_validate() writes."""
        cross_validate(api_db, concept="passengers_total")
        r = api_client.get("/cross-validations")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        row = body["items"][0]
        assert row["field_name"] == "passengers_total"
        assert row["primary_value"]["source_id"] == "caa_uk"
        assert row["agreement"] is True

    def test_filter_by_field_name(self, api_client, api_db, cv_db):
        cross_validate(api_db, concept="passengers_total")
        r = api_client.get("/cross-validations", params={"field_name": "nonexistent"})
        assert r.json()["total"] == 0
