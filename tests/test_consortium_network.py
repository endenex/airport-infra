"""Tests for Layer β.4 — Consortium Network Graph."""

import uuid
from datetime import date, datetime, timezone

import pytest

from analysis.consortium_network import compute_network
from backend.models import Airport, MethodologyVersion
from backend.models.transaction import Transaction


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
def lgw(api_db):
    a = Airport(
        id=uuid.uuid4(), iata_code="LGW", icao_code="EGKK",
        ourairports_ident="EGKK", name="London Gatwick",
        country_code="GB", tier=2,
    )
    api_db.add(a)
    api_db.commit()
    return a


def _txn(
    api_db, *, airport, buyers=None, sellers=None,
    state="closed", txn_type="acquisition",
) -> Transaction:
    mv = api_db.query(MethodologyVersion).first()
    t = Transaction(
        id=uuid.uuid4(),
        airport_id=airport.id if airport else None,
        asset_name=airport.iata_code if airport else "Unknown",
        announce_date=date(2024, 1, 1),
        close_date=date(2024, 6, 30),
        state=state, transaction_type=txn_type, currency="GBP",
        buyer_entities=buyers, seller_entities=sellers,
        source_url="https://x", retrieved_at=datetime.now(timezone.utc),
        methodology_version_id=mv.id,
    )
    api_db.add(t)
    api_db.commit()
    return t


# ── Edge formation ──────────────────────────────────────────────────────


class TestEdges:
    def test_two_buyers_same_deal_form_a_buyer_edge(self, api_db, lhr):
        _txn(api_db, airport=lhr, buyers=[
            {"name": "Ardian", "identifier_status": "identified"},
            {"name": "PIF",    "identifier_status": "identified"},
        ])
        nodes, edges = compute_network(api_db)
        assert len(nodes) == 2
        assert len(edges) == 1
        e = edges[0]
        # Names sorted for stable identity
        assert (e.party_a, e.party_b) == ("Ardian", "PIF")
        assert e.weight == 1
        assert e.sides == ["buyer"]
        assert e.airport_iatas == ["LHR"]

    def test_three_sellers_form_three_edges(self, api_db, lhr):
        """3 parties on the same side → C(3,2) = 3 edges."""
        _txn(api_db, airport=lhr, sellers=[
            {"name": "Ferrovial", "identifier_status": "identified"},
            {"name": "QIA",       "identifier_status": "identified"},
            {"name": "CDPQ",      "identifier_status": "identified"},
        ])
        _, edges = compute_network(api_db)
        assert len(edges) == 3
        names_in_edges = {tuple([e.party_a, e.party_b]) for e in edges}
        assert ("CDPQ", "Ferrovial") in names_in_edges
        assert ("CDPQ", "QIA") in names_in_edges
        assert ("Ferrovial", "QIA") in names_in_edges
        for e in edges:
            assert e.sides == ["seller"]

    def test_no_edge_across_sides(self, api_db, lhr):
        """A buyer and a seller in the same deal are NOT consortium partners."""
        _txn(api_db, airport=lhr,
             buyers=[{"name": "Ardian", "identifier_status": "identified"}],
             sellers=[{"name": "Ferrovial", "identifier_status": "identified"}])
        _, edges = compute_network(api_db)
        assert edges == []

    def test_same_pair_in_two_deals_increments_weight(self, api_db, lhr, lgw):
        """If two parties co-invest twice, edge weight = 2."""
        buyers = [
            {"name": "Ardian", "identifier_status": "identified"},
            {"name": "PIF",    "identifier_status": "identified"},
        ]
        _txn(api_db, airport=lhr, buyers=buyers)
        _txn(api_db, airport=lgw, buyers=buyers)
        _, edges = compute_network(api_db)
        assert len(edges) == 1
        assert edges[0].weight == 2
        assert sorted(edges[0].airport_iatas) == ["LGW", "LHR"]


# ── identifier_status discipline ────────────────────────────────────────


class TestIdentifierDiscipline:
    def test_rumored_party_excluded_by_default(self, api_db, lhr):
        """Layer γ rule: rumoured parties never get asserted into the network."""
        _txn(api_db, airport=lhr, buyers=[
            {"name": "ConfirmedCo", "identifier_status": "identified"},
            {"name": "RumourCo",    "identifier_status": "suspected"},
        ])
        nodes, edges = compute_network(api_db)
        assert [n.name for n in nodes] == ["ConfirmedCo"]
        # No edge — only one identified party
        assert edges == []

    def test_unknown_party_excluded_by_default(self, api_db, lhr):
        _txn(api_db, airport=lhr, buyers=[
            {"name": "ConfirmedCo", "identifier_status": "identified"},
            {"name": "UnnamedFund", "identifier_status": "unknown"},
        ])
        _, edges = compute_network(api_db)
        assert edges == []

    def test_include_unidentified_opens_the_gate(self, api_db, lhr):
        _txn(api_db, airport=lhr, buyers=[
            {"name": "ConfirmedCo", "identifier_status": "identified"},
            {"name": "RumourCo",    "identifier_status": "suspected"},
        ])
        nodes, edges = compute_network(api_db, include_unidentified=True)
        assert {n.name for n in nodes} == {"ConfirmedCo", "RumourCo"}
        assert len(edges) == 1


# ── State scope ─────────────────────────────────────────────────────────


class TestStateScope:
    def test_abandoned_deals_still_form_edges(self, api_db, lhr):
        """Per Appendix D, knowing who teamed up on a dead process is signal too."""
        _txn(api_db, airport=lhr, state="abandoned", buyers=[
            {"name": "PartyA", "identifier_status": "identified"},
            {"name": "PartyB", "identifier_status": "identified"},
        ])
        _, edges = compute_network(api_db)
        assert len(edges) == 1


# ── Node metadata ───────────────────────────────────────────────────────


class TestNodes:
    def test_node_deal_count_dedups_per_transaction(self, api_db, lhr):
        """A party appearing twice in same transaction (unlikely but possible) → 1 deal."""
        _txn(api_db, airport=lhr, buyers=[
            {"name": "PartyA", "identifier_status": "identified"},
        ])
        _txn(api_db, airport=lhr, buyers=[
            {"name": "PartyA", "identifier_status": "identified"},
        ])
        nodes, _ = compute_network(api_db)
        a = next(n for n in nodes if n.name == "PartyA")
        assert a.deal_count == 2  # two distinct transactions

    def test_sides_seen_tracks_role_history(self, api_db, lhr, lgw):
        """A party that's been both buyer and seller across deals."""
        _txn(api_db, airport=lhr,
             buyers=[{"name": "Flippy", "identifier_status": "identified"}])
        _txn(api_db, airport=lgw,
             sellers=[{"name": "Flippy", "identifier_status": "identified"}])
        nodes, _ = compute_network(api_db)
        flippy = next(n for n in nodes if n.name == "Flippy")
        assert sorted(flippy.sides_seen) == ["buyer", "seller"]

    def test_strategic_operator_flag_propagates(self, api_db, lhr):
        _txn(api_db, airport=lhr, buyers=[
            {"name": "VINCI Airports", "identifier_status": "identified",
             "is_strategic_operator": True},
        ])
        nodes, _ = compute_network(api_db)
        assert nodes[0].is_strategic_operator is True


# ── API surface ─────────────────────────────────────────────────────────


class TestApi:
    @pytest.fixture
    def seeded(self, api_db, lhr):
        _txn(api_db, airport=lhr, buyers=[
            {"name": "Ardian", "identifier_status": "identified"},
            {"name": "PIF",    "identifier_status": "identified"},
        ], sellers=[
            {"name": "Ferrovial", "identifier_status": "identified"},
            {"name": "QIA",       "identifier_status": "identified"},
        ])

    def test_endpoint_returns_shape(self, api_client, seeded):
        r = api_client.get("/capital-flows/consortium-network")
        assert r.status_code == 200
        body = r.json()
        assert "nodes" in body
        assert "edges" in body
        assert "methodology_notes" in body
        # 4 named parties; 1 buyer-edge + 1 seller-edge = 2 edges
        assert len(body["nodes"]) == 4
        assert len(body["edges"]) == 2

    def test_include_unidentified_param_propagates(self, api_client, api_db, lhr):
        _txn(api_db, airport=lhr, buyers=[
            {"name": "ConfirmedCo", "identifier_status": "identified"},
            {"name": "RumourCo",    "identifier_status": "suspected"},
        ])
        # default: rumoured excluded
        r = api_client.get("/capital-flows/consortium-network")
        assert r.json()["edges"] == []
        # with override: edge appears
        r = api_client.get("/capital-flows/consortium-network",
                           params={"include_unidentified": "true"})
        assert len(r.json()["edges"]) == 1

    def test_methodology_notes_always_present(self, api_client, seeded):
        r = api_client.get("/capital-flows/consortium-network")
        notes = " ".join(r.json()["methodology_notes"])
        assert "identifier_status" in notes  # honesty discipline disclosed
        assert "abandoned" in notes  # state scope disclosed
