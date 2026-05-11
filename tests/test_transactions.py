"""Tests for the transactions table, model, and API (Appendix D Layer γ)."""

import uuid

import pytest

from backend.models import Airport, MethodologyVersion
from backend.models.transaction import (
    VALID_FAILURE_STATUS,
    VALID_PRICE_CONFIDENCE,
    VALID_STATES,
    VALID_TRANSACTION_TYPES,
)


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


@pytest.fixture
def mv(api_db):
    return api_db.query(MethodologyVersion).first()


def _valid_body(**overrides):
    body = {
        "asset_name": "Test Asset",
        "state": "closed",
        "transaction_type": "acquisition",
        "source_url": "https://example.com/press-release",
        "buyer_entities": [
            {"name": "ACME Capital", "identifier_status": "identified"},
        ],
    }
    body.update(overrides)
    return body


class TestVocabularies:
    """Lock the lexicons — they're load-bearing for Layer γ semantics."""

    def test_states_include_all_counterfactual_kinds(self):
        # Per Appendix D #19, these MUST be present
        for kind in ("closed", "abandoned", "pulled", "bid_lost", "postponed"):
            assert kind in VALID_STATES

    def test_transaction_types_cover_main_axes(self):
        for kind in ("acquisition", "divestment", "refinancing"):
            assert kind in VALID_TRANSACTION_TYPES

    def test_price_confidence_lexicon(self):
        assert VALID_PRICE_CONFIDENCE == {"confirmed", "rumored", "range", "unknown"}

    def test_failure_status_lexicon(self):
        assert VALID_FAILURE_STATUS == {"disclosed", "inferred", "unknown"}


class TestCreate:
    def test_minimum_valid_transaction(self, api_client, lhr, mv):
        r = api_client.post("/transactions", json=_valid_body(airport_id=str(lhr.id)))
        assert r.status_code == 201
        body = r.json()
        assert body["state"] == "closed"
        assert body["asset_name"] == "Test Asset"
        assert body["airport_id"] == str(lhr.id)

    def test_rejects_invalid_state(self, api_client, mv):
        r = api_client.post("/transactions", json=_valid_body(state="garbage"))
        assert r.status_code == 422
        assert "state" in r.json()["detail"].lower()

    def test_rejects_invalid_transaction_type(self, api_client, mv):
        r = api_client.post("/transactions", json=_valid_body(transaction_type="garbage"))
        assert r.status_code == 422

    def test_rejects_invalid_price_confidence(self, api_client, mv):
        r = api_client.post(
            "/transactions",
            json=_valid_body(price_information_confidence="totally_made_up"),
        )
        assert r.status_code == 422

    def test_abandoned_with_reason_for_failure(self, api_client, mv):
        """The full counterfactual path — state=abandoned + inferred reason + suspected bidders."""
        r = api_client.post("/transactions", json=_valid_body(
            asset_name="Failed Process Airport",
            state="abandoned",
            transaction_type="minority_stake",
            reason_for_failure_status="inferred",
            reason_for_failure_text="Valuation expectations not met",
            buyer_entities=[],
            rival_bids=[
                {"name": "Macquarie", "identifier_status": "suspected",
                 "outcome": "withdrew", "price_confidence": "rumored"},
            ],
        ))
        assert r.status_code == 201
        body = r.json()
        assert body["state"] == "abandoned"
        assert body["reason_for_failure_status"] == "inferred"
        assert body["rival_bids"][0]["identifier_status"] == "suspected"
        assert body["rival_bids"][0]["price_confidence"] == "rumored"

    def test_rejects_invalid_reason_for_failure_status(self, api_client, mv):
        r = api_client.post("/transactions", json=_valid_body(
            state="abandoned", reason_for_failure_status="totally_made_up",
        ))
        assert r.status_code == 422


class TestList:
    @pytest.fixture
    def seeded(self, api_client, lhr, mv):
        # Closed acquisition on LHR
        api_client.post("/transactions", json=_valid_body(
            airport_id=str(lhr.id), asset_name="LHR closed deal 2024",
            announce_date="2024-11-28", close_date="2024-12-17",
            state="closed", transaction_type="acquisition",
        ))
        # Abandoned process (no airport linkage)
        api_client.post("/transactions", json=_valid_body(
            asset_name="Failed process 2022", announce_date="2022-06-01",
            state="abandoned", transaction_type="minority_stake",
            buyer_entities=[], reason_for_failure_status="inferred",
        ))
        # Refinancing on LHR 2023
        api_client.post("/transactions", json=_valid_body(
            airport_id=str(lhr.id), asset_name="LHR refi 2023",
            announce_date="2023-03-07", close_date="2023-03-14",
            state="closed", transaction_type="refinancing", buyer_entities=[],
        ))

    def test_list_all(self, api_client, seeded):
        r = api_client.get("/transactions")
        assert r.status_code == 200
        assert r.json()["total"] == 3

    def test_filter_by_iata(self, api_client, seeded):
        r = api_client.get("/transactions", params={"iata": "LHR"})
        assert r.json()["total"] == 2

    def test_filter_by_state_abandoned(self, api_client, seeded):
        """Layer γ canonical query: 'show me deals that didn't close'."""
        r = api_client.get("/transactions", params={"state": "abandoned"})
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["state"] == "abandoned"

    def test_filter_by_transaction_type(self, api_client, seeded):
        r = api_client.get("/transactions", params={"transaction_type": "refinancing"})
        assert r.json()["total"] == 1

    def test_filter_by_year_matches_announce_or_close(self, api_client, seeded):
        r = api_client.get("/transactions", params={"year": 2022})
        assert r.json()["total"] == 1
        r = api_client.get("/transactions", params={"year": 2024})
        assert r.json()["total"] == 1

    def test_unknown_iata_returns_empty(self, api_client, seeded):
        r = api_client.get("/transactions", params={"iata": "ZZZ"})
        assert r.status_code == 200
        assert r.json()["total"] == 0


class TestDetail:
    def test_get_by_id(self, api_client, lhr, mv):
        created = api_client.post("/transactions", json=_valid_body(airport_id=str(lhr.id))).json()
        r = api_client.get(f"/transactions/{created['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_unknown_id_404(self, api_client, mv):
        r = api_client.get("/transactions/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_garbage_id_404_not_500(self, api_client, mv):
        r = api_client.get("/transactions/not-a-uuid")
        assert r.status_code == 404


class TestCounterfactualSchemaIntegrity:
    """
    Lock the structural invariants Appendix D #19 depends on. If a future
    refactor splits counterfactuals off into a separate table or strips
    one of the required fields, these break loudly.
    """

    def test_can_persist_rumored_bidder_without_asserting(self, api_client, mv):
        """A rumored bidder must travel with identifier_status=suspected/unknown."""
        r = api_client.post("/transactions", json=_valid_body(
            asset_name="Rumour-only process",
            state="rumored",
            buyer_entities=[],
            rival_bids=[
                {"name": "Unnamed Sponsor", "identifier_status": "suspected",
                 "price_confidence": "rumored"},
            ],
        ))
        assert r.status_code == 201
        bid = r.json()["rival_bids"][0]
        # Critical: identifier_status MUST be preserved exactly as submitted —
        # otherwise we risk silently upgrading a rumour to "identified".
        assert bid["identifier_status"] == "suspected"

    def test_dates_independent_state_announce_close(self, api_client, mv):
        """An abandoned process can have announce_date but no close_date."""
        r = api_client.post("/transactions", json=_valid_body(
            asset_name="Open-ended abandoned",
            announce_date="2022-06-01",
            close_date=None,
            state="abandoned",
            buyer_entities=[],
        ))
        body = r.json()
        assert body["announce_date"] == "2022-06-01"
        assert body["close_date"] is None
