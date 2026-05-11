"""Unit tests for the CONCESSION extraction pipeline parse_response."""

import json
from unittest.mock import MagicMock

from llm_pipelines.concession_extraction import (
    CONCESSION_CONCEPTS,
    ConcessionExtractionPipeline,
)

SAMPLE_CONTEXT = {
    "entity_name": "Heathrow Airport Limited",
    "entity_key_prefix": "caa_h7_final_decision_summary",
    "source_url": "https://example.com/cap2524a.pdf",
    "source_document_id": "abc123" + "0" * 58,
    "reporting_period_end": "2023-03-08",
    "regulator_name": "UK Civil Aviation Authority",
    "regulatory_framework_name": "H7",
    "regulatory_period_start": "2022-01-01",
    "regulatory_period_end": "2026-12-31",
    "airport_id": None,
}


def _llm_response(*extractions: dict, document_currency: str | None = "GBP") -> str:
    """Build an LLM-response JSON envelope. v1.1 includes document_currency."""
    payload: dict = {"extractions": list(extractions)}
    if document_currency is not None:
        payload["document_currency"] = document_currency
    return json.dumps(payload)


def _pipeline() -> ConcessionExtractionPipeline:
    return ConcessionExtractionPipeline(client=MagicMock())


class TestParseResponse:
    def test_period_scoped_concept_uses_regulatory_period_from_context(self):
        """WACC is a regulatory-period-scoped concept; periods come from the Disclosure, not the LLM."""
        response = _llm_response({
            "concept": "allowed_wacc_vanilla_pct",
            "value": 3.18,
            "unit": "percent",
            # Even though the LLM omits a period_end, we must populate it from context
            "confidence": 0.95,
            "evidence_quote": "The vanilla WACC for H7 is 3.18%.",
        })
        records = _pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert len(records) == 1
        r = records[0]
        assert r.period_start == "2022-01-01"
        assert r.period_end == "2026-12-31"
        assert r.payload["concept"] == "allowed_wacc_vanilla_pct"
        assert r.payload["value"] == 3.18
        assert r.payload["regulator_name"] == "UK Civil Aviation Authority"
        assert r.payload["regulatory_framework_name"] == "H7"

    def test_annual_concept_uses_llm_period(self):
        """forecast_passengers_pax is annual; periods come from the LLM (per-year row)."""
        response = _llm_response(
            {"concept": "forecast_passengers_pax", "value": 61_600_000,
             "unit": "passengers", "period_end": "2022-12-31", "confidence": 0.95},
            {"concept": "forecast_passengers_pax", "value": 81_300_000,
             "unit": "passengers", "period_end": "2026-12-31", "confidence": 0.95},
        )
        records = _pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert len(records) == 2
        first = next(r for r in records if r.period_end == "2022-12-31")
        last = next(r for r in records if r.period_end == "2026-12-31")
        assert first.payload["value"] == 61_600_000.0
        assert last.payload["value"] == 81_300_000.0

    def test_annual_concept_without_period_end_is_dropped(self):
        response = _llm_response(
            {"concept": "forecast_capex_million", "value": 367,
             "confidence": 0.95, "unit": "million"},  # no period_end
        )
        assert _pipeline().parse_response(response, SAMPLE_CONTEXT) == []

    def test_drops_unknown_concept(self):
        response = _llm_response(
            {"concept": "shareholder_dividend", "value": 100,
             "confidence": 0.9, "period_end": "2025-12-31"},
            {"concept": "allowed_wacc_vanilla_pct", "value": 3.18, "confidence": 0.95},
        )
        records = _pipeline().parse_response(response, SAMPLE_CONTEXT)
        assert len(records) == 1
        assert records[0].payload["concept"] == "allowed_wacc_vanilla_pct"

    def test_drops_non_numeric_value(self):
        response = _llm_response(
            {"concept": "allowed_wacc_vanilla_pct", "value": "not a number",
             "confidence": 0.5},
        )
        assert _pipeline().parse_response(response, SAMPLE_CONTEXT) == []

    def test_evidence_quote_excluded_from_payload(self):
        """Same idempotency invariant as climate/operational pipelines."""
        response = _llm_response({
            "concept": "allowed_wacc_vanilla_pct", "value": 3.18,
            "confidence": 0.95, "evidence_quote": "WACC is 3.18%",
        })
        r = _pipeline().parse_response(response, SAMPLE_CONTEXT)[0]
        assert "evidence_quote" not in r.payload
        assert "evidence_quote" in r.raw_llm_response

    def test_record_type_and_pipeline_metadata(self):
        response = _llm_response({
            "concept": "allowed_wacc_vanilla_pct", "value": 3.18, "confidence": 0.95,
        })
        r = _pipeline().parse_response(response, SAMPLE_CONTEXT)[0]
        assert r.record_type == "CONCESSION"

    def test_framework_name_in_payload_is_part_of_identity(self):
        """
        Two different price-control periods (H7 vs hypothetical H8) for the
        same airport must produce different records, so framework_name must
        flow into the payload (hashed) — not just metadata.
        """
        response = _llm_response({
            "concept": "allowed_wacc_vanilla_pct", "value": 3.18, "confidence": 0.95,
        })
        r1 = _pipeline().parse_response(response, SAMPLE_CONTEXT)[0]
        ctx2 = {**SAMPLE_CONTEXT, "regulatory_framework_name": "H8"}
        r2 = _pipeline().parse_response(response, ctx2)[0]
        assert r1.payload["regulatory_framework_name"] != r2.payload["regulatory_framework_name"]


def test_pipeline_declares_record_type():
    assert ConcessionExtractionPipeline.record_type == "CONCESSION"


def test_pipeline_version_is_v1_1():
    """v1.1 = currency-agnostic concept names + per-record currency field."""
    assert ConcessionExtractionPipeline.prompt_version == "1.1"


def test_concept_allowlist_consistency():
    """Each allowlisted concept has a recognized scope."""
    valid_scopes = {"regulatory_period", "annual"}
    for concept, scope in CONCESSION_CONCEPTS.items():
        assert scope in valid_scopes, f"{concept}: unknown scope {scope}"


def test_no_concept_hardcodes_a_currency():
    """
    v1.1 invariant: concept names must NOT embed a currency code.
    Currency travels in the per-record `currency` field.
    """
    currency_codes = {"gbp", "eur", "usd", "chf", "jpy", "cad", "aud"}
    for concept in CONCESSION_CONCEPTS:
        tokens = concept.lower().split("_")
        offending = currency_codes.intersection(tokens)
        assert not offending, (
            f"Concept {concept!r} embeds currency tokens {offending}. "
            f"Use a currency-agnostic name and rely on payload.currency."
        )


class TestCurrencyHandling:
    def test_monetary_concept_carries_document_currency(self):
        response = _llm_response(
            {"concept": "capex_allowance_total_million", "value": 3620,
             "unit": "million", "confidence": 0.95},
            document_currency="GBP",
        )
        r = _pipeline().parse_response(response, SAMPLE_CONTEXT)[0]
        assert r.payload["currency"] == "GBP"
        assert r.payload["value"] == 3620.0

    def test_monetary_concept_dropped_when_currency_missing(self):
        """A capex figure without a currency is ambiguous — refuse to persist."""
        response = _llm_response(
            {"concept": "capex_allowance_total_million", "value": 3620,
             "unit": "million", "confidence": 0.95},
            document_currency=None,
        )
        assert _pipeline().parse_response(response, SAMPLE_CONTEXT) == []

    def test_non_monetary_concept_currency_is_null(self):
        """WACC and pax counts don't need currency — leave null in payload."""
        response = _llm_response(
            {"concept": "allowed_wacc_vanilla_pct", "value": 3.18,
             "unit": "percent", "confidence": 0.95},
            document_currency="GBP",
        )
        r = _pipeline().parse_response(response, SAMPLE_CONTEXT)[0]
        assert r.payload["currency"] is None

    def test_eur_document_currency_propagates(self):
        """AENA DORA II is in EUR; that must flow into payload."""
        response = _llm_response(
            {"concept": "regulated_asset_base_opening_million", "value": 9858.9,
             "unit": "million", "confidence": 0.95},
            document_currency="EUR",
        )
        r = _pipeline().parse_response(response, SAMPLE_CONTEXT)[0]
        assert r.payload["currency"] == "EUR"

    def test_currency_uppercased_and_trimmed(self):
        """Robust against 'eur', ' GBP ', etc. — normalise to upper/strip."""
        response = _llm_response(
            {"concept": "capex_allowance_total_million", "value": 100,
             "unit": "million", "confidence": 0.95},
            document_currency="  eur  ",
        )
        r = _pipeline().parse_response(response, SAMPLE_CONTEXT)[0]
        assert r.payload["currency"] == "EUR"
