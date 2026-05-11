"""Unit tests for the OPERATIONAL extraction pipeline parse_response."""

import json
from unittest.mock import MagicMock

from llm_pipelines.operational_extraction import (
    OPERATIONAL_CONCEPTS,
    OperationalExtractionPipeline,
)

SAMPLE_CONTEXT = {
    "entity_name": "Heathrow Airport Holdings",
    "entity_key_prefix": "heathrow:sustainability_2025",
    "source_url": "https://example.com/sustainability.pdf",
    "source_document_id": "abc123" + "0" * 58,
    "reporting_period_end": "2025-12-31",
    "airport_id": None,
}


def _llm_response(*extractions: dict) -> str:
    return json.dumps({"extractions": list(extractions)})


def _make_pipeline() -> OperationalExtractionPipeline:
    return OperationalExtractionPipeline(client=MagicMock())


class TestParseResponse:
    def test_happy_path_passengers(self):
        response = _llm_response(
            {
                "concept": "passengers_total",
                "value": 79212440,
                "unit": "passengers",
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "confidence": 0.95,
                "evidence_quote": "Total passengers in 2024 were 79.2 million (79,212,440)",
            }
        )
        records = _make_pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert len(records) == 1
        r = records[0]
        assert r.record_type == "OPERATIONAL"
        assert r.payload["concept"] == "passengers_total"
        assert r.payload["value"] == 79212440.0
        assert r.payload["unit"] == "passengers"
        assert r.confidence_score == 0.95
        assert "evidence_quote" not in r.payload  # noise → raw_llm_response only
        assert r.raw_llm_response is not None
        assert "evidence_quote" in r.raw_llm_response

    def test_drops_unknown_concept(self):
        response = _llm_response(
            {"concept": "load_factor_percent", "value": 87.0,
             "confidence": 0.9, "period_end": "2024-12-31"},
            {"concept": "passengers_total", "value": 50000000,
             "confidence": 0.95, "period_end": "2024-12-31"},
        )
        records = _make_pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert len(records) == 1
        assert records[0].payload["concept"] == "passengers_total"

    def test_drops_non_numeric_value(self):
        response = _llm_response(
            {"concept": "cargo_tonnes", "value": "n/a", "confidence": 0.5,
             "period_end": "2024-12-31"},
        )
        assert _make_pipeline().parse_response(response, SAMPLE_CONTEXT) == []

    def test_drops_non_positive_value(self):
        """Pax / movements / cargo counts must be strictly positive."""
        response = _llm_response(
            {"concept": "passengers_total", "value": 0, "confidence": 0.9,
             "period_end": "2024-12-31"},
            {"concept": "passengers_total", "value": -100, "confidence": 0.9,
             "period_end": "2024-12-31"},
        )
        assert _make_pipeline().parse_response(response, SAMPLE_CONTEXT) == []

    def test_clamps_confidence(self):
        response = _llm_response(
            {"concept": "air_transport_movements", "value": 500000, "confidence": 1.5,
             "period_end": "2024-12-31"},
            {"concept": "cargo_tonnes", "value": 1700000, "confidence": -0.1,
             "period_end": "2024-12-31"},
        )
        records = _make_pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert records[0].confidence_score == 1.0
        assert records[1].confidence_score == 0.0

    def test_entity_key_includes_concept_and_period(self):
        response = _llm_response(
            {"concept": "passengers_total", "value": 79000000, "confidence": 0.95,
             "period_end": "2024-12-31"},
            {"concept": "passengers_total", "value": 78000000, "confidence": 0.95,
             "period_end": "2023-12-31"},
        )
        records = _make_pipeline().parse_response(response, SAMPLE_CONTEXT)
        # Same concept, different periods → different entity_key, both kept
        assert records[0].entity_key != records[1].entity_key
        assert "2024-12-31" in records[0].entity_key
        assert "2023-12-31" in records[1].entity_key

    def test_invalid_json_returns_empty(self):
        records = _make_pipeline().parse_response("not json", SAMPLE_CONTEXT)
        assert records == []


def test_pipeline_declares_record_type():
    """Runner relies on this attribute to scope the cache check."""
    assert OperationalExtractionPipeline.record_type == "OPERATIONAL"


def test_allowed_concepts_list_is_documented():
    """Guard against silent drift between the prompt's concept list and the allow-list."""
    expected = {
        "passengers_total",
        "passengers_domestic",
        "passengers_international",
        "passengers_transfer",
        "air_transport_movements",
        "aircraft_movements_total",
        "cargo_tonnes",
    }
    assert set(OPERATIONAL_CONCEPTS) == expected
