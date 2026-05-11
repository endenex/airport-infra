"""Tests for Layer β.1 — Fund Vintage Maturity Wall."""

import uuid
from datetime import date, datetime, timezone

import pytest

from analysis.fund_vintage_wall import (
    DEFAULT_HOLD_MAX_YEARS,
    DEFAULT_HOLD_MEDIAN_YEARS,
    DEFAULT_HOLD_MIN_YEARS,
    aggregate_by_exit_year,
    compute_holdings,
)
from backend.models import Airport, MethodologyVersion
from backend.models.transaction import Transaction


@pytest.fixture
def brs(api_db):
    a = Airport(
        id=uuid.uuid4(), iata_code="BRS", icao_code="EGGD",
        ourairports_ident="EGGD", name="Bristol Airport",
        country_code="GB", tier=4,
    )
    api_db.add(a)
    api_db.commit()
    return a


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


def _make_txn(
    api_db, *, airport, asset_name: str, state: str, txn_type: str,
    buyer_entities: list[dict], close_year: int | None = None,
    seller_entities: list[dict] | None = None,
    continuing_holders: list[dict] | None = None,
) -> Transaction:
    mv = api_db.query(MethodologyVersion).first()
    txn = Transaction(
        id=uuid.uuid4(),
        airport_id=airport.id if airport else None,
        asset_name=asset_name,
        announce_date=date(close_year, 12, 1) if close_year else None,
        close_date=date(close_year, 12, 19) if (close_year and state == "closed") else None,
        state=state,
        transaction_type=txn_type,
        currency="GBP",
        buyer_entities=buyer_entities,
        seller_entities=seller_entities,
        continuing_holders=continuing_holders,
        source_url="https://example.com/x",
        retrieved_at=datetime.now(timezone.utc),
        methodology_version_id=mv.id,
    )
    api_db.add(txn)
    api_db.commit()
    return txn


# ── compute_holdings ────────────────────────────────────────────────────


class TestComputeHoldings:
    def test_extracts_buyer_with_fund_vintage(self, api_db, brs):
        _make_txn(
            api_db, airport=brs, asset_name="BRS 50% IFM acq",
            state="closed", txn_type="acquisition", close_year=2014,
            buyer_entities=[{
                "name": "IFM Investors", "identifier_status": "identified",
                "is_strategic_operator": False,
                "fund_name": "IFM Global Infrastructure Fund",
                "fund_vintage": 2007, "equity_stake_pct": 50.0,
            }],
        )
        holdings = compute_holdings(api_db, today=date(2024, 7, 1))
        assert len(holdings) == 1
        h = holdings[0]
        assert h.airport_iata == "BRS"
        assert h.holder_name == "IFM Investors"
        assert h.fund_vintage == 2007
        assert h.current_stake_pct == 50.0  # v2: cumulative current stake
        assert h.first_established_year == 2014
        # Holding age: mid-2024 - vintage 2007 ≈ 17.5y
        assert 17 < h.holding_age_years < 18
        # Median exit: 2007 + 10 = 2017
        assert h.expected_exit_year == 2017
        # Window: [2007+8, 2007+12] = [2015, 2019]
        assert h.expected_exit_window == [2015, 2019]
        # Maturity capped at 100% (we're 7.5y past expected exit)
        assert h.maturity_pct == 100.0

    def test_excludes_strategic_operators(self, api_db, brs):
        """VINCI is a strategic operator — no vintage exit signature."""
        _make_txn(
            api_db, airport=brs, asset_name="Strategic acquirer",
            state="closed", txn_type="acquisition", close_year=2024,
            buyer_entities=[{
                "name": "VINCI Airports", "identifier_status": "identified",
                "is_strategic_operator": True,
                "fund_name": None, "fund_vintage": None,
            }],
        )
        assert compute_holdings(api_db, today=date(2024, 7, 1)) == []

    def test_excludes_buyer_without_vintage(self, api_db, brs):
        """If LLM couldn't extract vintage, we silently omit — no fabrication."""
        _make_txn(
            api_db, airport=brs, asset_name="Mystery fund",
            state="closed", txn_type="acquisition", close_year=2020,
            buyer_entities=[{
                "name": "Some Anonymous Fund", "identifier_status": "identified",
                "is_strategic_operator": False, "fund_name": "Unknown Fund I",
                "fund_vintage": None,  # missing vintage — exclude
            }],
        )
        assert compute_holdings(api_db, today=date(2024, 7, 1)) == []

    def test_excludes_signed_state_transactions(self, api_db, brs):
        """
        v2: signed-but-not-closed deals are forward-looking, NOT held
        positions. v1 incorrectly counted them; v2 fixes this via the
        holdings replay (closed-only).
        """
        _make_txn(
            api_db, airport=brs, asset_name="Signed deal",
            state="signed", txn_type="acquisition", close_year=2024,
            buyer_entities=[{
                "name": "Recent Fund", "is_strategic_operator": False,
                "identifier_status": "identified",
                "fund_vintage": 2020, "equity_stake_pct": 100.0,
            }],
        )
        assert compute_holdings(api_db, today=date(2024, 7, 1)) == []

    def test_excludes_counterfactual_states(self, api_db, brs):
        """Abandoned / pulled / rumored don't represent positions taken."""
        _make_txn(
            api_db, airport=brs, asset_name="Process that failed",
            state="abandoned", txn_type="acquisition",
            buyer_entities=[{
                "name": "Macquarie", "is_strategic_operator": False,
                "fund_vintage": 2018, "equity_stake_pct": 50.0,
            }],
        )
        assert compute_holdings(api_db, today=date(2024, 7, 1)) == []

    def test_excludes_refinancing(self, api_db, brs):
        """Refinancings aren't ownership changes — no new holding."""
        _make_txn(
            api_db, airport=brs, asset_name="Bond refi",
            state="closed", txn_type="refinancing",
            buyer_entities=[{
                "name": "Bond Co", "is_strategic_operator": False,
                "fund_vintage": 2020,
            }],
        )
        assert compute_holdings(api_db, today=date(2024, 7, 1)) == []

    def test_consortium_yields_one_holding_per_buyer_with_vintage(self, api_db, lhr):
        """Two LPs in a consortium both with vintage = 2 holdings; strategic + 1 LP = 1 holding."""
        _make_txn(
            api_db, airport=lhr, asset_name="LHR consortium acq",
            state="closed", txn_type="acquisition", close_year=2024,
            buyer_entities=[
                {"name": "Ardian", "is_strategic_operator": False,
                 "fund_vintage": 2019, "equity_stake_pct": 22.6,
                 "identifier_status": "identified"},
                {"name": "PIF", "is_strategic_operator": False,
                 "fund_vintage": 2018, "equity_stake_pct": 15.0,
                 "identifier_status": "identified"},
                # Strategic — excluded
                {"name": "Some Operator", "is_strategic_operator": True,
                 "equity_stake_pct": 5.0, "identifier_status": "identified"},
            ],
        )
        holdings = compute_holdings(api_db, today=date(2024, 7, 1))
        names = sorted(h.holder_name for h in holdings)
        assert names == ["Ardian", "PIF"]

    def test_v2_aggregates_cross_transaction_acquisitions(self, api_db, brs):
        """
        v2 fix: a fund buying 30% in 2018 + 20% in 2022 → ONE current position
        at 50%. v1 showed two separate FundHoldings.
        """
        for year, pct in [(2018, 30.0), (2022, 20.0)]:
            _make_txn(
                api_db, airport=brs,
                asset_name=f"BRS partial acq {year}",
                state="closed", txn_type="acquisition", close_year=year,
                buyer_entities=[{
                    "name": "Patient Fund", "identifier_status": "identified",
                    "is_strategic_operator": False,
                    "fund_name": "Patient Infra Fund", "fund_vintage": 2015,
                    "equity_stake_pct": pct,
                }],
            )
        holdings = compute_holdings(api_db, today=date(2024, 7, 1))
        assert len(holdings) == 1  # ONE position, not two
        assert holdings[0].current_stake_pct == 50.0  # cumulative
        assert holdings[0].first_established_year == 2018  # first event

    def test_v2_surfaces_continuing_holder_with_vintage(self, api_db, lhr):
        """
        v2 fix: a continuing holder with vintage data now appears. v1 only
        looked at buyer_entities and missed continuing-holder positions.
        """
        _make_txn(
            api_db, airport=lhr, asset_name="LHR deal",
            state="closed", txn_type="acquisition", close_year=2024,
            buyer_entities=[{
                "name": "Active Buyer", "is_strategic_operator": True,
                "identifier_status": "identified",
                "equity_stake_pct": 50.0,
            }],
            continuing_holders=[{
                "name": "Long-standing LP", "identifier_status": "identified",
                "is_strategic_operator": False,
                "fund_name": "Steady Hand Fund IV", "fund_vintage": 2015,
                "post_transaction_stake_pct": 50.0,
            }],
        )
        holdings = compute_holdings(api_db, today=date(2024, 7, 1))
        # Strategic buyer excluded; continuing LP holder appears
        assert len(holdings) == 1
        assert holdings[0].holder_name == "Long-standing LP"
        assert holdings[0].current_stake_pct == 50.0
        assert holdings[0].fund_vintage == 2015

    def test_assumption_overrides_propagate(self, api_db, brs):
        """User can override the 10-year median — Assumption Lab style."""
        _make_txn(
            api_db, airport=brs, asset_name="BRS acq",
            state="closed", txn_type="acquisition", close_year=2018,
            buyer_entities=[{
                "name": "Long-hold Fund", "identifier_status": "identified",
                "is_strategic_operator": False,
                "fund_vintage": 2015, "equity_stake_pct": 30.0,
            }],
        )
        h = compute_holdings(
            api_db, today=date(2024, 7, 1),
            hold_median_years=15, hold_min_years=12, hold_max_years=18,
        )[0]
        assert h.expected_exit_year == 2030  # vintage + 15
        assert h.expected_exit_window == [2027, 2033]
        # 9.5y / 15y ≈ 63%
        assert 60 < h.maturity_pct < 66


# ── aggregate_by_exit_year ──────────────────────────────────────────────


class TestAggregate:
    def test_groups_by_exit_year(self, api_db, brs, lhr):
        _make_txn(
            api_db, airport=brs, asset_name="BRS 2014 acq",
            state="closed", txn_type="acquisition", close_year=2014,
            buyer_entities=[{"name": "IFM", "identifier_status": "identified",
                             "is_strategic_operator": False,
                             "fund_vintage": 2007, "equity_stake_pct": 50.0}],
        )
        # Same expected exit year (vintage 2007 + 10 = 2017)
        _make_txn(
            api_db, airport=lhr, asset_name="LHR 2014 acq",
            state="closed", txn_type="acquisition", close_year=2014,
            buyer_entities=[{"name": "IFM-Fund-II", "identifier_status": "identified",
                             "is_strategic_operator": False,
                             "fund_vintage": 2007, "equity_stake_pct": 10.0}],
        )
        holdings = compute_holdings(api_db, today=date(2024, 7, 1))
        buckets = aggregate_by_exit_year(holdings)
        assert len(buckets) == 1
        assert buckets[0].year == 2017
        assert buckets[0].count == 2
        assert sorted(buckets[0].airports) == ["BRS", "LHR"]


# ── API surface ─────────────────────────────────────────────────────────


class TestFundVintageWallApi:
    @pytest.fixture
    def seeded(self, api_db, brs):
        _make_txn(
            api_db, airport=brs, asset_name="BRS IFM 2014",
            state="closed", txn_type="acquisition", close_year=2014,
            buyer_entities=[{
                "name": "IFM Investors", "identifier_status": "identified",
                "is_strategic_operator": False,
                "fund_name": "IFM Global Infrastructure Fund",
                "fund_vintage": 2007, "equity_stake_pct": 50.0,
            }],
        )

    def test_endpoint_returns_shape(self, api_client, seeded):
        r = api_client.get("/capital-flows/fund-vintage-wall",
                           params={"today": "2024-07-01"})
        assert r.status_code == 200
        body = r.json()
        assert "holdings" in body
        assert "by_exit_year" in body
        assert "assumptions" in body
        assert "methodology_notes" in body
        assert len(body["holdings"]) == 1
        h = body["holdings"][0]
        assert h["airport_iata"] == "BRS"
        assert h["fund_vintage"] == 2007

    def test_assumption_overrides_via_query_param(self, api_client, seeded):
        r = api_client.get(
            "/capital-flows/fund-vintage-wall",
            params={"today": "2024-07-01", "hold_median_years": 15,
                    "hold_min_years": 12, "hold_max_years": 18},
        )
        body = r.json()
        h = body["holdings"][0]
        # vintage 2007 + 15 = 2022
        assert h["expected_exit_year"] == 2022
        assert body["assumptions"]["hold_median_years"] == 15

    def test_methodology_notes_always_present(self, api_client, seeded):
        """Per Appendix D — assumptions travel with the data so users can defend it."""
        r = api_client.get("/capital-flows/fund-vintage-wall")
        notes = r.json()["methodology_notes"]
        joined = " ".join(notes)
        # Critical disclosures that should be persistent
        assert "Strategic operators" in joined
        # v2 acknowledges its provenance via the holdings reconciliation
        assert "holdings" in joined.lower()
        assert "fund_vintage" in joined  # absence note


def test_default_assumption_constants_are_sane():
    """If the defaults drift, downstream consumers (charts, IC papers) will too."""
    assert DEFAULT_HOLD_MIN_YEARS < DEFAULT_HOLD_MEDIAN_YEARS < DEFAULT_HOLD_MAX_YEARS
    assert 6 <= DEFAULT_HOLD_MIN_YEARS <= 12
    assert 8 <= DEFAULT_HOLD_MEDIAN_YEARS <= 14
    assert 10 <= DEFAULT_HOLD_MAX_YEARS <= 16
