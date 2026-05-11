"""Tests for the ingestion base harness."""

from datetime import datetime, timezone
from typing import Any

from ingestion.base import IngestorBase, RawRecord


class StubIngestor(IngestorBase):
    source_id = "test_source"

    def __init__(self, records: list[RawRecord]):
        self._records = records

    def fetch(self) -> Any:
        return self._records

    def parse(self, raw: Any) -> list[RawRecord]:
        return raw


def make_record(entity_key: str = "LHR", payload: dict | None = None) -> RawRecord:
    return RawRecord(
        entity_key=entity_key,
        source_url="https://example.com/test.pdf",
        source_document_id="doc-001",
        retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        record_type="FINANCIAL",
        payload=payload or {"revenue": 1000, "year": 2024},
    )


class TestRecordId:
    def test_same_inputs_produce_same_id(self):
        ingestor = StubIngestor([])
        record = make_record()
        assert ingestor.record_id(record) == ingestor.record_id(record)

    def test_different_payload_produces_different_id(self):
        ingestor = StubIngestor([])
        r1 = make_record(payload={"revenue": 1000})
        r2 = make_record(payload={"revenue": 2000})
        assert ingestor.record_id(r1) != ingestor.record_id(r2)

    def test_different_entity_key_produces_different_id(self):
        ingestor = StubIngestor([])
        r1 = make_record(entity_key="LHR")
        r2 = make_record(entity_key="CDG")
        assert ingestor.record_id(r1) != ingestor.record_id(r2)

    def test_id_is_48_chars(self):
        ingestor = StubIngestor([])
        record = make_record()
        assert len(ingestor.record_id(record)) == 48


class TestIngestionRun:
    def test_idempotency(self, db_session):
        record = make_record()
        ingestor = StubIngestor([record])

        result1 = ingestor.run(db_session)
        result2 = ingestor.run(db_session)

        assert result1.records_created == 1
        assert result1.records_skipped == 0
        assert result2.records_created == 0
        assert result2.records_skipped == 1

    def test_result_success_on_clean_run(self, db_session):
        record = make_record(entity_key="CDG_TEST")
        ingestor = StubIngestor([record])
        result = ingestor.run(db_session)
        assert result.success is True
        assert result.records_fetched == 1

    def test_intra_batch_duplicates_are_deduped(self, db_session):
        """
        Two records with identical entity_key + payload + retrieval_date hash
        to the same ID. The base must dedupe them within the same batch —
        db.get() misses pending (unflushed) objects, so an in-memory check is
        required to avoid a PK collision at commit time.
        """
        r1 = make_record(entity_key="AMS_DUP", payload={"revenue": 999, "year": 2024})
        r2 = make_record(entity_key="AMS_DUP", payload={"revenue": 999, "year": 2024})
        ingestor = StubIngestor([r1, r2])
        result = ingestor.run(db_session)
        assert result.success is True
        assert result.records_created == 1
        assert result.records_skipped == 1

    def test_failed_run_resets_counts(self, db_session):
        """On rollback the result must not report records as created."""

        class ExplodingIngestor(IngestorBase):
            source_id = "exploding"

            def fetch(self) -> Any:
                return [make_record(entity_key="EXPLODE_1"), make_record(entity_key="EXPLODE_2")]

            def parse(self, raw: Any) -> list[RawRecord]:
                raise RuntimeError("parse blew up")

        result = ExplodingIngestor().run(db_session)
        assert result.success is False
        assert result.records_created == 0
        assert result.records_skipped == 0
        assert any("parse blew up" in e for e in result.errors)
