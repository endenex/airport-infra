"""Unit tests for the LLM transaction-extraction pipeline (parser + persist)."""

import json
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from backend.models import Airport
from backend.models.transaction import Transaction
from llm_pipelines.transaction_extraction import (
    TransactionExtraction,
    TransactionExtractionPipeline,
    _coerce_party_list,
    _parse_date,
    _parse_response_json,
    _resolve_airport_id,
)

# ── JSON envelope parser ─────────────────────────────────────────────────


class TestParseResponseJson:
    def test_plain_json(self):
        assert _parse_response_json('{"transaction": {}}') == {"transaction": {}}

    def test_strips_code_fence(self):
        assert _parse_response_json('```json\n{"x": 1}\n```') == {"x": 1}


# ── Date parser ──────────────────────────────────────────────────────────


class TestParseDate:
    def test_iso_date(self):
        assert _parse_date("2024-06-25") == date(2024, 6, 25)

    def test_none(self):
        assert _parse_date(None) is None

    def test_garbage_returns_none(self):
        assert _parse_date("not a date") is None
        assert _parse_date("06/25/2024") is None


# ── Party normalisation ──────────────────────────────────────────────────


class TestCoercePartyList:
    def test_empty_returns_none(self):
        assert _coerce_party_list(None) is None
        assert _coerce_party_list([]) is None

    def test_drops_entries_without_name(self):
        result = _coerce_party_list([
            {"name": "VINCI Airports", "identifier_status": "identified"},
            {"identifier_status": "identified"},  # no name → dropped
            {"name": "", "identifier_status": "identified"},  # empty name → dropped
        ])
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "VINCI Airports"

    def test_clamps_invalid_identifier_status_to_unknown(self):
        """Critical for Layer γ honesty discipline — never silently asserts."""
        result = _coerce_party_list([
            {"name": "ACME", "identifier_status": "totally_made_up"},
            {"name": "BCM", "identifier_status": "definitely_real"},
        ])
        assert result[0]["identifier_status"] == "unknown"
        assert result[1]["identifier_status"] == "unknown"

    def test_preserves_valid_identifier_statuses(self):
        result = _coerce_party_list([
            {"name": "A", "identifier_status": "identified"},
            {"name": "B", "identifier_status": "suspected"},
            {"name": "C", "identifier_status": "unknown"},
        ])
        statuses = [p["identifier_status"] for p in result]
        assert statuses == ["identified", "suspected", "unknown"]

    def test_defaults_missing_identifier_status_to_unknown(self):
        result = _coerce_party_list([{"name": "X"}])
        assert result[0]["identifier_status"] == "unknown"


# ── Airport resolution ──────────────────────────────────────────────────


@pytest.fixture
def edi(api_db):
    a = Airport(
        id=uuid.uuid4(), iata_code="EDI", icao_code="EGPH",
        ourairports_ident="EGPH", name="Edinburgh Airport",
        country_code="GB", tier=3,
    )
    api_db.add(a)
    api_db.commit()
    return a


class TestResolveAirportId:
    def test_known_iata_returns_id(self, api_db, edi):
        assert _resolve_airport_id(api_db, "EDI") == edi.id

    def test_lowercase_iata_works(self, api_db, edi):
        assert _resolve_airport_id(api_db, "edi") == edi.id

    def test_unknown_iata_returns_none(self, api_db, edi):
        assert _resolve_airport_id(api_db, "ZZZ") is None

    def test_none_returns_none(self, api_db, edi):
        assert _resolve_airport_id(api_db, None) is None

    def test_garbage_returns_none(self, api_db, edi):
        assert _resolve_airport_id(api_db, "TOO_LONG") is None


# ── End-to-end persist (mocked LLM, real DB) ─────────────────────────────


def _stub_extraction(**overrides) -> TransactionExtraction:
    """A canonical extraction shape mirroring the VINCI/Edinburgh real run."""
    parsed = {
        "asset_name": "Edinburgh Airport (50.01% majority stake)",
        "iata_hint": "EDI",
        "state": "closed",
        "transaction_type": "acquisition",
        "announce_date": "2024-04-17",
        "close_date": "2024-06-25",
        "equity_value": 1270000000,
        "currency": "GBP",
        "stake_percent": 50.01,
        "price_information_confidence": "confirmed",
        "buyer_entities": [
            {"name": "VINCI Airports", "role": "lead",
             "identifier_status": "identified",
             "source_quote": "VINCI Airports finalised the acquisition"},
        ],
        "seller_entities": [
            {"name": "GIP Edinburgh Airport Holdings", "role": "lead",
             "identifier_status": "identified", "equity_stake_pct": 50.01},
        ],
        "rival_bids": [],
        "overall_extraction_confidence": 0.95,
        "evidence_summary": "VINCI acquired 50.01% of Edinburgh Airport for £1.27bn",
    }
    parsed.update(overrides.get("parsed", {}))
    return TransactionExtraction(
        parsed=parsed,
        overall_confidence=overrides.get("overall_confidence", 0.95),
        evidence_summary=parsed["evidence_summary"],
        raw_response={"transaction": parsed},
    )


class TestPersist:
    def test_writes_row_with_full_provenance(self, api_db, edi):
        pipeline = TransactionExtractionPipeline(client=MagicMock())
        row = pipeline.persist(
            api_db, _stub_extraction(),
            source_url="https://example.com/vinci.html",
            source_document_id="abc123" * 8,
        )
        assert isinstance(row, Transaction)
        assert row.airport_id == edi.id
        assert row.state == "closed"
        assert row.transaction_type == "acquisition"
        assert row.announce_date == date(2024, 4, 17)
        assert row.close_date == date(2024, 6, 25)
        assert float(row.equity_value) == 1_270_000_000.0
        assert row.currency == "GBP"
        assert row.stake_percent == 50.01
        assert row.price_information_confidence == "confirmed"
        assert row.source_url == "https://example.com/vinci.html"
        assert row.methodology_version_id is not None
        # Notes carry the overall_confidence + evidence_summary
        assert "0.95" in (row.notes or "")
        assert "Edinburgh" in (row.notes or "")

    def test_falls_back_to_rumored_on_invalid_state(self, api_db, edi):
        """LLM hallucinating an out-of-lexicon state must not crash persistence."""
        pipeline = TransactionExtractionPipeline(client=MagicMock())
        extraction = _stub_extraction(parsed={"state": "definitely_real_state"})
        row = pipeline.persist(
            api_db, extraction,
            source_url="https://example.com/x", source_document_id="doc",
        )
        assert row.state == "rumored"

    def test_falls_back_to_other_on_invalid_transaction_type(self, api_db, edi):
        pipeline = TransactionExtractionPipeline(client=MagicMock())
        extraction = _stub_extraction(parsed={"transaction_type": "totally_invented"})
        row = pipeline.persist(
            api_db, extraction,
            source_url="https://example.com/x", source_document_id="doc",
        )
        assert row.transaction_type == "other"

    def test_unresolvable_iata_lands_unlinked(self, api_db, edi):
        """A press release for an airport we don't have should not 500; row lands without airport_id."""
        pipeline = TransactionExtractionPipeline(client=MagicMock())
        extraction = _stub_extraction(parsed={"iata_hint": "ZZZ"})
        row = pipeline.persist(
            api_db, extraction,
            source_url="https://example.com/x", source_document_id="doc",
        )
        assert row.airport_id is None
        assert row.state == "closed"  # other fields still extracted


# ── extract() with mocked Anthropic client ───────────────────────────────


class TestExtractEndToEnd:
    def test_extract_parses_anthropic_response(self):
        """Validate the full extract() path with a mocked Anthropic response."""
        client = MagicMock()
        client.messages.create.return_value.content = [
            MagicMock(text=json.dumps({
                "transaction": {
                    "asset_name": "Test Asset",
                    "iata_hint": "LHR",
                    "state": "closed",
                    "transaction_type": "acquisition",
                    "announce_date": "2024-01-01",
                    "close_date": "2024-01-31",
                    "buyer_entities": [
                        {"name": "Buyer Co", "identifier_status": "identified",
                         "role": "lead"},
                    ],
                    "seller_entities": [],
                    "rival_bids": [
                        {"name": "Rival Co", "identifier_status": "suspected",
                         "outcome": "withdrew", "price_confidence": "rumored"},
                    ],
                    "overall_extraction_confidence": 0.88,
                    "evidence_summary": "Concrete sentence."
                }
            }))
        ]
        pipeline = TransactionExtractionPipeline(client=client)
        result = pipeline.extract("dummy document text", source_url="https://x.com/r")
        assert result.parsed["state"] == "closed"
        assert result.overall_confidence == 0.88
        assert result.parsed["rival_bids"][0]["identifier_status"] == "suspected"
        client.messages.create.assert_called_once()
        call = client.messages.create.call_args
        # Temperature pinned to 0 for deterministic re-runs
        assert call.kwargs["temperature"] == 0.0
