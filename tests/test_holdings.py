"""Tests for analysis.holdings (transaction replay → current holdings)."""

import uuid
from datetime import date, datetime, timezone

import pytest

from analysis.consortium_network import compute_co_ownership_network
from analysis.holdings import (
    compute_current_holdings,
    reconcile_stakes,
)
from backend.models import Airport, MethodologyVersion
from backend.models.transaction import Transaction


@pytest.fixture
def lhr(api_db):
    a = Airport(id=uuid.uuid4(), iata_code="LHR", icao_code="EGLL",
                ourairports_ident="EGLL", name="London Heathrow",
                country_code="GB", tier=1)
    api_db.add(a)
    api_db.commit()
    return a


@pytest.fixture
def lgw(api_db):
    a = Airport(id=uuid.uuid4(), iata_code="LGW", icao_code="EGKK",
                ourairports_ident="EGKK", name="London Gatwick",
                country_code="GB", tier=2)
    api_db.add(a)
    api_db.commit()
    return a


def _txn(
    api_db, *, airport, when: date, state="closed", txn_type="acquisition",
    buyers=None, sellers=None, continuing=None,
) -> Transaction:
    mv = api_db.query(MethodologyVersion).first()
    t = Transaction(
        id=uuid.uuid4(),
        airport_id=airport.id if airport else None,
        asset_name=airport.iata_code if airport else "Unknown",
        announce_date=when,
        signing_date=when,
        close_date=when if state == "closed" else None,
        state=state, transaction_type=txn_type, currency="GBP",
        buyer_entities=buyers, seller_entities=sellers,
        continuing_holders=continuing,
        source_url="https://x", retrieved_at=datetime.now(timezone.utc),
        methodology_version_id=mv.id,
    )
    api_db.add(t)
    api_db.commit()
    return t


# ── Holdings replay ─────────────────────────────────────────────────────


class TestHoldingsReplay:
    def test_single_buyer_creates_position(self, api_db, lhr):
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "Buyer Co", "identifier_status": "identified",
             "equity_stake_pct": 50.0},
        ])
        holdings = compute_current_holdings(api_db)
        assert len(holdings) == 1
        assert holdings[0].holder_name == "Buyer Co"
        assert holdings[0].current_stake_pct == 50.0

    def test_seller_reduces_position(self, api_db, lhr):
        """Buyer acquires 60% then sells 20% — should hold 40%."""
        _txn(api_db, airport=lhr, when=date(2020, 1, 1), buyers=[
            {"name": "Trader", "identifier_status": "identified",
             "equity_stake_pct": 60.0},
        ])
        _txn(api_db, airport=lhr, when=date(2023, 1, 1), sellers=[
            {"name": "Trader", "identifier_status": "identified",
             "equity_stake_pct": 20.0},
        ])
        holdings = compute_current_holdings(api_db)
        assert len(holdings) == 1
        assert holdings[0].current_stake_pct == 40.0

    def test_full_exit_removes_position(self, api_db, lhr):
        _txn(api_db, airport=lhr, when=date(2020, 1, 1), buyers=[
            {"name": "Trader", "identifier_status": "identified",
             "equity_stake_pct": 100.0},
        ])
        _txn(api_db, airport=lhr, when=date(2023, 1, 1), sellers=[
            {"name": "Trader", "identifier_status": "identified",
             "equity_stake_pct": 100.0},
        ])
        # Result: stake = 0%, position dropped
        assert compute_current_holdings(api_db) == []

    def test_continuing_holder_seeds_position(self, api_db, lhr):
        """Edinburgh case: VINCI acquires; GIP remains as continuing holder."""
        _txn(api_db, airport=lhr, when=date(2024, 6, 25), buyers=[
            {"name": "VINCI Airports", "identifier_status": "identified",
             "equity_stake_pct": 50.01, "is_strategic_operator": True},
        ], continuing=[
            {"name": "GIP", "identifier_status": "identified",
             "post_transaction_stake_pct": 49.99},
        ])
        holdings = compute_current_holdings(api_db)
        names = {h.holder_name: h.current_stake_pct for h in holdings}
        assert names == {"VINCI Airports": 50.01, "GIP": 49.99}

    def test_continuing_holder_not_double_counted_across_transactions(
        self, api_db, lhr
    ):
        """If GIP is mentioned as continuing in 2 transactions, only seed once."""
        _txn(api_db, airport=lhr, when=date(2020, 1, 1), buyers=[
            {"name": "Buyer1", "identifier_status": "identified",
             "equity_stake_pct": 10},
        ], continuing=[
            {"name": "GIP", "identifier_status": "identified",
             "post_transaction_stake_pct": 90},
        ])
        # Second transaction also lists GIP as continuing
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "Buyer2", "identifier_status": "identified",
             "equity_stake_pct": 5},
        ], continuing=[
            {"name": "GIP", "identifier_status": "identified",
             "post_transaction_stake_pct": 90},
        ])
        holdings = compute_current_holdings(api_db)
        gip = next(h for h in holdings if h.holder_name == "GIP")
        # Only the first seed counts (so GIP at 90, not 180)
        assert gip.current_stake_pct == 90.0

    def test_only_closed_transactions_feed_holdings(self, api_db, lhr):
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), state="signed", buyers=[
            {"name": "Pending Buyer", "identifier_status": "identified",
             "equity_stake_pct": 50.0},
        ])
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), state="abandoned", buyers=[
            {"name": "Failed Buyer", "identifier_status": "identified",
             "equity_stake_pct": 50.0},
        ])
        assert compute_current_holdings(api_db) == []

    def test_unidentified_party_excluded_by_default(self, api_db, lhr):
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "Real Buyer", "identifier_status": "identified",
             "equity_stake_pct": 50.0},
            {"name": "Rumour Buyer", "identifier_status": "suspected",
             "equity_stake_pct": 25.0},
        ])
        holdings = compute_current_holdings(api_db)
        assert [h.holder_name for h in holdings] == ["Real Buyer"]

    def test_distinct_funds_of_same_manager_tracked_separately(self, api_db, lhr):
        """MIP III and MIP IV are different positions even if both 'Macquarie'."""
        _txn(api_db, airport=lhr, when=date(2018, 1, 1), buyers=[
            {"name": "Macquarie", "identifier_status": "identified",
             "fund_name": "MIP III", "equity_stake_pct": 25.0},
        ])
        _txn(api_db, airport=lhr, when=date(2022, 1, 1), buyers=[
            {"name": "Macquarie", "identifier_status": "identified",
             "fund_name": "MIP IV", "equity_stake_pct": 15.0},
        ])
        holdings = compute_current_holdings(api_db)
        assert len(holdings) == 2
        funds = sorted(h.fund_name for h in holdings)
        assert funds == ["MIP III", "MIP IV"]

    def test_provenance_trail_preserved(self, api_db, lhr):
        """Holding.established_via captures every transaction that touched it."""
        _txn(api_db, airport=lhr, when=date(2020, 1, 1), buyers=[
            {"name": "Trader", "identifier_status": "identified",
             "equity_stake_pct": 60.0},
        ])
        _txn(api_db, airport=lhr, when=date(2023, 1, 1), sellers=[
            {"name": "Trader", "identifier_status": "identified",
             "equity_stake_pct": 20.0},
        ])
        h = compute_current_holdings(api_db)[0]
        assert len(h.established_via) == 2
        sides = [e.side for e in h.established_via]
        assert sides == ["buyer", "seller"]
        # Final stake = 40 — reflected in last event's new_total_pct
        assert h.established_via[-1].new_total_pct == 40.0


# ── Co-ownership network (uses holdings) ────────────────────────────────


class TestCoOwnership:
    def test_cross_transaction_edge_now_visible(self, api_db, lhr):
        """The β.4 gap fix: separate transactions, same airport, edge forms."""
        _txn(api_db, airport=lhr, when=date(2018, 1, 1), buyers=[
            {"name": "Fund A", "identifier_status": "identified",
             "equity_stake_pct": 50.0},
        ])
        _txn(api_db, airport=lhr, when=date(2022, 1, 1), buyers=[
            {"name": "Fund B", "identifier_status": "identified",
             "equity_stake_pct": 30.0},
        ])
        _nodes, edges = compute_co_ownership_network(api_db)
        # Holdings-based network sees Fund A and Fund B as co-owners of LHR
        # even though they bought in different transactions.
        assert len(edges) == 1
        e = edges[0]
        assert (e.party_a, e.party_b) == ("Fund A", "Fund B")
        assert e.shared_airports == ["LHR"]

    def test_separate_airports_no_edge(self, api_db, lhr, lgw):
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "Fund A", "identifier_status": "identified",
             "equity_stake_pct": 100.0},
        ])
        _txn(api_db, airport=lgw, when=date(2024, 1, 1), buyers=[
            {"name": "Fund B", "identifier_status": "identified",
             "equity_stake_pct": 100.0},
        ])
        _, edges = compute_co_ownership_network(api_db)
        assert edges == []

    def test_two_shared_airports_increments_weight(self, api_db, lhr, lgw):
        """If A and B co-own both LHR and LGW, edge.shared_airport_count = 2."""
        for airport in (lhr, lgw):
            _txn(api_db, airport=airport, when=date(2024, 1, 1), buyers=[
                {"name": "Fund A", "identifier_status": "identified",
                 "equity_stake_pct": 50.0},
                {"name": "Fund B", "identifier_status": "identified",
                 "equity_stake_pct": 50.0},
            ])
        _, edges = compute_co_ownership_network(api_db)
        assert len(edges) == 1
        assert edges[0].shared_airport_count == 2
        assert sorted(edges[0].shared_airports) == ["LGW", "LHR"]

    def test_continuing_holder_appears_in_edges(self, api_db, lhr):
        """The Edinburgh-style case: VINCI buys, GIP continues → edge between them."""
        _txn(api_db, airport=lhr, when=date(2024, 6, 25), buyers=[
            {"name": "VINCI Airports", "identifier_status": "identified",
             "equity_stake_pct": 50.01, "is_strategic_operator": True},
        ], continuing=[
            {"name": "GIP", "identifier_status": "identified",
             "post_transaction_stake_pct": 49.99},
        ])
        _, edges = compute_co_ownership_network(api_db)
        assert len(edges) == 1
        assert sorted([edges[0].party_a, edges[0].party_b]) == [
            "GIP", "VINCI Airports",
        ]


# ── Stake reconciliation ────────────────────────────────────────────────


class TestReconcileStakes:
    def test_balanced_airport(self, api_db, lhr):
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "Owner A", "identifier_status": "identified",
             "equity_stake_pct": 60.0},
            {"name": "Owner B", "identifier_status": "identified",
             "equity_stake_pct": 40.0},
        ])
        recs = reconcile_stakes(compute_current_holdings(api_db))
        assert len(recs) == 1
        assert recs[0].status == "balanced"
        assert recs[0].total_held_pct == 100.0
        assert recs[0].holder_count == 2

    def test_under_allocated_flags(self, api_db, lhr):
        """Only 60% accounted for → missing data signal."""
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "Solo Buyer", "identifier_status": "identified",
             "equity_stake_pct": 60.0},
        ])
        recs = reconcile_stakes(compute_current_holdings(api_db))
        assert recs[0].status == "under_allocated"
        assert recs[0].deviation_from_100_pct == -40.0

    def test_over_allocated_flags(self, api_db, lhr):
        """Sum > 100% → extraction error somewhere upstream."""
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "Greedy A", "identifier_status": "identified",
             "equity_stake_pct": 70.0},
            {"name": "Greedy B", "identifier_status": "identified",
             "equity_stake_pct": 50.0},
        ])
        recs = reconcile_stakes(compute_current_holdings(api_db))
        assert recs[0].status == "over_allocated"
        assert recs[0].deviation_from_100_pct == 20.0

    def test_tolerance_band_treats_near_100_as_balanced(self, api_db, lhr):
        """A 0.5% gap from rounding shouldn't trip the flag."""
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "Owner A", "identifier_status": "identified",
             "equity_stake_pct": 50.01},
            {"name": "Owner B", "identifier_status": "identified",
             "equity_stake_pct": 49.5},
        ])
        # Default tolerance 1.0%; deviation = -0.49 → balanced
        recs = reconcile_stakes(compute_current_holdings(api_db))
        assert recs[0].status == "balanced"

    def test_results_sorted_by_absolute_deviation(self, api_db, lhr, lgw):
        _txn(api_db, airport=lhr, when=date(2024, 1, 1), buyers=[
            {"name": "X", "identifier_status": "identified",
             "equity_stake_pct": 60.0},  # -40% deviation
        ])
        _txn(api_db, airport=lgw, when=date(2024, 1, 1), buyers=[
            {"name": "Y", "identifier_status": "identified",
             "equity_stake_pct": 30.0},  # -70% deviation
        ])
        recs = reconcile_stakes(compute_current_holdings(api_db))
        # LGW has bigger absolute deviation → comes first
        assert recs[0].airport_iata == "LGW"
        assert recs[1].airport_iata == "LHR"


# ── API surface ─────────────────────────────────────────────────────────


class TestApi:
    @pytest.fixture
    def seeded(self, api_db, lhr):
        # Two separate transactions on same airport → co-ownership edge
        _txn(api_db, airport=lhr, when=date(2018, 1, 1), buyers=[
            {"name": "Fund A", "identifier_status": "identified",
             "equity_stake_pct": 50.0},
        ])
        _txn(api_db, airport=lhr, when=date(2022, 1, 1), buyers=[
            {"name": "Fund B", "identifier_status": "identified",
             "equity_stake_pct": 30.0},
        ])

    def test_co_ownership_endpoint(self, api_client, seeded):
        r = api_client.get("/capital-flows/co-ownership-network")
        body = r.json()
        assert len(body["edges"]) == 1
        assert len(body["nodes"]) == 2

    def test_current_holdings_endpoint(self, api_client, seeded):
        r = api_client.get("/capital-flows/current-holdings")
        body = r.json()
        assert len(body["holdings"]) == 2
        names = {h["holder_name"] for h in body["holdings"]}
        assert names == {"Fund A", "Fund B"}
        # Provenance preserved per holding
        for h in body["holdings"]:
            assert len(h["established_via"]) >= 1

    def test_reconciliation_in_response(self, api_client, seeded):
        """The seeded fixture has 50% + 30% = 80% total → under_allocated flag."""
        r = api_client.get("/capital-flows/current-holdings")
        body = r.json()
        assert "reconciliation" in body
        assert len(body["reconciliation"]) == 1
        rec = body["reconciliation"][0]
        assert rec["airport_iata"] == "LHR"
        assert rec["total_held_pct"] == 80.0
        assert rec["status"] == "under_allocated"
        assert rec["deviation_from_100_pct"] == -20.0
        assert body["reconciliation_tolerance_pct"] == 1.0

    def test_reconciliation_tolerance_override(self, api_client, seeded):
        """A 30% tolerance band makes the 20% deviation 'balanced'."""
        r = api_client.get(
            "/capital-flows/current-holdings",
            params={"reconciliation_tolerance_pct": 30},
        )
        body = r.json()
        assert body["reconciliation"][0]["status"] == "balanced"
