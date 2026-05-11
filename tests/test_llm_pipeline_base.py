"""Tests for the LLM pipeline base — confidence routing and review queue."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from llm_pipelines.base import ExtractedRecord, ExtractionResult, LLMPipelineBase


class StubPipeline(LLMPipelineBase):
    prompt_version = "1.0"

    def build_messages(self, document: str, context: dict) -> list[dict]:
        return [{"role": "user", "content": document}]

    def parse_response(self, response_text: str, context: dict) -> list[ExtractedRecord]:
        return [
            ExtractedRecord(
                entity_key="LHR",
                source_url="https://example.com/doc.pdf",
                source_document_id="doc-001",
                retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                record_type="CLIMATE",
                payload={"scope_1_emissions_tco2e": 5000},
                confidence_score=0.92,
            )
        ]


def make_extracted(confidence: float, entity_key: str = "LHR") -> ExtractedRecord:
    return ExtractedRecord(
        entity_key=entity_key,
        source_url="https://example.com/doc.pdf",
        source_document_id="doc-001",
        retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        record_type="CLIMATE",
        payload={"scope_1_emissions_tco2e": 5000},
        confidence_score=confidence,
    )


class TestConfidenceRouting:
    def test_high_confidence_routes_to_auto_approved(self):
        pipeline = StubPipeline(client=MagicMock())
        record = make_extracted(confidence=0.90)
        assert pipeline.route(record) == "auto_approved"

    def test_low_confidence_routes_to_pending_review(self):
        pipeline = StubPipeline(client=MagicMock())
        record = make_extracted(confidence=0.70)
        assert pipeline.route(record) == "pending_review"

    def test_exactly_at_threshold_is_auto_approved(self):
        pipeline = StubPipeline(client=MagicMock())
        # threshold is 0.85 by default; exact match should approve
        record = make_extracted(confidence=0.85)
        assert pipeline.route(record) == "auto_approved"


class TestExtractionResult:
    def test_auto_approved_and_pending_split(self):
        result = ExtractionResult(
            records=[
                make_extracted(0.92, "LHR"),
                make_extracted(0.70, "CDG"),
                make_extracted(0.85, "AMS"),
            ]
        )
        assert len(result.auto_approved) == 2
        assert len(result.pending_review) == 1
        assert result.pending_review[0].entity_key == "CDG"
