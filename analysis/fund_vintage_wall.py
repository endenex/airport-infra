"""
Layer β.1 — Fund Vintage Maturity Wall (Appendix D Layer β).

v2 (current commit): rebuilt on the holdings reconciliation layer.
Earlier v1 looped buyer_entities directly from transactions and missed
two cases:
  - Continuing holders (e.g. GIP's 49.99% of EDI as continuing_holder
    on the VINCI deal) — never appeared in buyer_entities so never
    surfaced. v2 sees them via analysis.holdings.compute_current_holdings.
  - Cumulative positions (Fund A buys 30% in 2018 and 20% in 2022 →
    one position, 50%). v1 produced two separate "holdings" with stake
    fields meaning "amount acquired in that transaction". v2 produces
    one position with the current cumulative stake.

Methodology v2:
  - Median hold = 10y; window = vintage + 8y to vintage + 12y (typical
    infrastructure-fund range).
  - Strategic operators (VINCI, Vinci Airports, AENA Internacional etc.)
    are EXCLUDED — they don't exit on a vintage clock.
  - Closed transactions only (per holdings replay). signed-but-not-closed
    deals are forward-looking, not held positions.
  - Funds without fund_vintage data are silently omitted. Absence here
    is not evidence of absence from the market.

Run: uv run python -m analysis.fund_vintage_wall
"""

import argparse
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from analysis.holdings import compute_current_holdings
from backend.db.connection import SessionLocal

logger = logging.getLogger(__name__)

# Tunable defaults — per Appendix D #17 these eventually live in
# assumption_sets so the Assumption Laboratory can override.
DEFAULT_HOLD_MIN_YEARS = 8
DEFAULT_HOLD_MEDIAN_YEARS = 10
DEFAULT_HOLD_MAX_YEARS = 12


@dataclass
class FundHolding:
    """One fund-backed position derived from current holdings."""

    airport_iata: str | None
    airport_name: str | None
    holder_name: str
    fund_name: str | None
    fund_vintage: int
    first_established_year: int | None  # year position originally established
    current_stake_pct: float            # cumulative current stake (after replay)
    holding_age_years: float            # today - vintage
    expected_exit_year: int             # vintage + median hold
    expected_exit_window: list[int]     # [vintage + min, vintage + max]
    maturity_pct: float                 # 0-100; capped at 100
    transaction_ids: list[str]          # all transactions that touched the position


@dataclass
class MaturityWallBucket:
    """Count of holdings expected to exit in a given calendar year."""

    year: int
    count: int
    airports: list[str]
    holder_names: list[str]


def compute_holdings(
    db: Session,
    *,
    today: date | None = None,
    hold_min_years: int = DEFAULT_HOLD_MIN_YEARS,
    hold_median_years: int = DEFAULT_HOLD_MEDIAN_YEARS,
    hold_max_years: int = DEFAULT_HOLD_MAX_YEARS,
) -> list[FundHolding]:
    """
    Build fund-vintage positions from CURRENT holdings (reconciled by
    analysis.holdings.compute_current_holdings).

    Each output row = one (airport, fund) current position. A fund that
    accumulated its stake across multiple transactions appears once with
    the cumulative current_stake_pct. Continuing-holder positions (e.g.
    GIP carried over a VINCI deal) appear too if vintage data is on the
    continuing_holders entry.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()

    out: list[FundHolding] = []
    for h in compute_current_holdings(db):
        if h.is_strategic_operator:
            continue
        if not isinstance(h.fund_vintage, int):
            continue
        vintage = h.fund_vintage
        holding_age = (today.year - vintage) + (today.month - 1) / 12.0
        expected_exit = vintage + hold_median_years
        window = [vintage + hold_min_years, vintage + hold_max_years]
        maturity_pct = min(100.0, max(0.0, holding_age / hold_median_years * 100))

        out.append(FundHolding(
            airport_iata=h.airport_iata,
            airport_name=h.airport_name,
            holder_name=h.holder_name,
            fund_name=h.fund_name,
            fund_vintage=vintage,
            first_established_year=(
                h.first_established.year if h.first_established else None
            ),
            current_stake_pct=h.current_stake_pct,
            holding_age_years=round(holding_age, 2),
            expected_exit_year=expected_exit,
            expected_exit_window=window,
            maturity_pct=round(maturity_pct, 1),
            transaction_ids=[ev.transaction_id for ev in h.established_via],
        ))
    return out


def aggregate_by_exit_year(holdings: list[FundHolding]) -> list[MaturityWallBucket]:
    """Roll holdings up by expected_exit_year — the 'maturity wall' itself."""
    buckets: dict[int, MaturityWallBucket] = {}
    for h in holdings:
        b = buckets.setdefault(
            h.expected_exit_year,
            MaturityWallBucket(year=h.expected_exit_year, count=0, airports=[], holder_names=[]),
        )
        b.count += 1
        if h.airport_iata:
            b.airports.append(h.airport_iata)
        b.holder_names.append(h.holder_name)
    return sorted(buckets.values(), key=lambda b: b.year)


def methodology_notes(
    hold_min: int, hold_median: int, hold_max: int,
) -> list[str]:
    return [
        f"Hold period assumption: median {hold_median}y, range {hold_min}-{hold_max}y "
        "(typical for infrastructure funds; v1 default).",
        "Strategic operators (e.g. VINCI Airports, AENA Internacional) excluded — "
        "they don't exit on a vintage clock.",
        "v2 (current): positions derived from current reconciled holdings "
        "(analysis/holdings.py replay). Closes the v1 gap where continuing "
        "holders and cross-transaction accumulations were invisible. "
        "Divestments now net correctly against earlier acquisitions.",
        "Only CLOSED transactions feed the holdings replay. signed-but-"
        "not-yet-closed deals are forward-looking, not held positions.",
        "Only holders with explicit fund_vintage data appear. Funds where "
        "the LLM couldn't extract vintage are silently omitted; absence "
        "here is not evidence of absence from the market.",
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--today", help="Override 'today' for the calculation (YYYY-MM-DD)")
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else None

    db = SessionLocal()
    try:
        holdings = compute_holdings(db, today=today)
        buckets = aggregate_by_exit_year(holdings)

        print(f"\n=== Fund Vintage Maturity Wall ({len(holdings)} fund-backed positions) ===\n")
        if not holdings:
            print("  No holdings — no current holdings with fund_vintage data.")
        for h in holdings:
            print(
                f"  {h.airport_iata or '?':>4} "
                f"{h.holder_name[:30]:30s} "
                f"vintage={h.fund_vintage} "
                f"established={h.first_established_year}  "
                f"stake={h.current_stake_pct:5.1f}%  "
                f"age={h.holding_age_years:4.1f}y  "
                f"maturity={h.maturity_pct:5.1f}%  "
                f"exit≈{h.expected_exit_year} ({h.expected_exit_window[0]}-{h.expected_exit_window[1]})"
            )

        print("\n=== Maturity wall — exits by year ===\n")
        for b in buckets:
            print(f"  {b.year}: {b.count} position(s) → {', '.join(b.airports) or '?'}")

        print("\n=== Methodology notes ===")
        for n in methodology_notes(
            DEFAULT_HOLD_MIN_YEARS, DEFAULT_HOLD_MEDIAN_YEARS, DEFAULT_HOLD_MAX_YEARS,
        ):
            print(f"  - {n}")
    finally:
        db.close()
