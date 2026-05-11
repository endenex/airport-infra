"""Unit tests for the CLIMATE extraction pipeline parse_response."""

import json
from unittest.mock import MagicMock

from llm_pipelines.climate_extraction import (
    CLIMATE_CONCEPTS,
    ClimateExtractionPipeline,
    _parse_response_json,
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


def _make_pipeline() -> ClimateExtractionPipeline:
    return ClimateExtractionPipeline(client=MagicMock())


class TestParseResponseJson:
    def test_plain_json(self):
        assert _parse_response_json('{"extractions": []}') == {"extractions": []}

    def test_strips_json_code_fence(self):
        wrapped = '```json\n{"extractions": [{"x": 1}]}\n```'
        assert _parse_response_json(wrapped) == {"extractions": [{"x": 1}]}

    def test_strips_bare_code_fence(self):
        wrapped = '```\n{"extractions": []}\n```'
        assert _parse_response_json(wrapped) == {"extractions": []}

    def test_extracts_json_block_from_chatter(self):
        text = 'Sure, here you go:\n{"extractions": [{"y": 2}]}\nLet me know if you need more.'
        assert _parse_response_json(text) == {"extractions": [{"y": 2}]}


class TestParseResponse:
    def test_happy_path_well_formed_record(self):
        response = _llm_response(
            {
                "concept": "scope_1_emissions_tco2e",
                "value": 26681,
                "unit": "tCO2e",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "confidence": 0.95,
                "evidence_quote": "Total scope 1 greenhouse gas emissions 26,681",
            }
        )
        records = _make_pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert len(records) == 1
        r = records[0]
        assert r.payload["concept"] == "scope_1_emissions_tco2e"
        assert r.payload["value"] == 26681.0
        assert r.payload["unit"] == "tCO2e"
        assert r.period_start == "2025-01-01"
        assert r.period_end == "2025-12-31"
        assert r.confidence_score == 0.95
        assert r.record_type == "CLIMATE"
        # evidence_quote must live in raw_llm_response, NOT payload — it's
        # text that can vary across runs and would break idempotency.
        assert "evidence_quote" not in r.payload
        assert r.raw_llm_response is not None
        assert "evidence_quote" in r.raw_llm_response

    def test_drops_unknown_concept(self):
        response = _llm_response(
            {"concept": "carbon_offset_credits", "value": 100, "confidence": 0.9, "period_end": "2025-12-31"},
            {"concept": "scope_1_emissions_tco2e", "value": 26681, "confidence": 0.95, "period_end": "2025-12-31"},
        )
        records = _make_pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert len(records) == 1
        assert records[0].payload["concept"] == "scope_1_emissions_tco2e"

    def test_drops_non_numeric_value(self):
        response = _llm_response(
            {"concept": "scope_1_emissions_tco2e", "value": "n/a", "confidence": 0.5, "period_end": "2025-12-31"},
        )
        assert _make_pipeline().parse_response(response, SAMPLE_CONTEXT) == []

    def test_clamps_confidence_to_unit_interval(self):
        response = _llm_response(
            {"concept": "scope_1_emissions_tco2e", "value": 100, "confidence": 1.5, "period_end": "2025-12-31"},
            {"concept": "scope_2_emissions_market_based_tco2e", "value": 50, "confidence": -0.2, "period_end": "2025-12-31"},
        )
        records = _make_pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert records[0].confidence_score == 1.0
        assert records[1].confidence_score == 0.0

    def test_entity_key_includes_concept_and_period(self):
        response = _llm_response(
            {"concept": "scope_1_emissions_tco2e", "value": 100, "confidence": 0.9, "period_end": "2025-12-31"},
            {"concept": "scope_1_emissions_tco2e", "value": 95, "confidence": 0.9, "period_end": "2024-12-31"},
        )
        records = _make_pipeline().parse_response(response, SAMPLE_CONTEXT)
        # Same concept, different period → different entity_key, both kept
        assert records[0].entity_key != records[1].entity_key
        assert "2025-12-31" in records[0].entity_key
        assert "2024-12-31" in records[1].entity_key

    def test_invalid_json_returns_empty(self):
        records = _make_pipeline().parse_response("this is not json", SAMPLE_CONTEXT)
        assert records == []


def test_allowed_concepts_list_is_documented():
    """Guard against silent drift between the prompt's concept list and the allow-list."""
    expected = {
        "scope_1_emissions_tco2e",
        "scope_2_emissions_location_based_tco2e",
        "scope_2_emissions_market_based_tco2e",
        "scope_3_emissions_tco2e",
        "total_emissions_tco2e",
        "renewable_energy_percent",
        "net_zero_target_year",
    }
    assert set(CLIMATE_CONCEPTS) == expected
