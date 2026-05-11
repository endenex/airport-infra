"""Tests for the ingestion base harness."""

from datetime import datetime, timezone
from typing import Any

import pytest

from ingestion.base import IngestorBase, RawRecord, IngestionResult


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
