"""
Layer β.1 — Fund Vintage Maturity Wall (Appendix D Layer β).

Computes per-transaction "holdings" with maturity metadata: for each
closed/signed acquisition where the buyer carries a fund_vintage, derive
holding age, expected exit window, and maturity-percent.

Methodology v1 — intentionally honest about limitations:
  - Median hold = 10y; window = vintage + 8y to vintage + 12y (typical
    infrastructure-fund range).
  - Strategic operators (VINCI, Vinci Airports, AENA Internacional etc.)
    are EXCLUDED from this view — they don't exit on a vintage clock.
  - We do NOT yet net acquisitions against divestments for the same fund.
    A fund that bought into airport A and later sold its stake will still
    appear as a "current position" here. v2 should reconcile via the
    transactions table once we have richer ownership chains.
  - Only acquisitions from transactions table feed this. Pre-existing
    holdings inferred from CONCESSION / OWNERSHIP records aren't included.

Run: uv run python -m analysis.fund_vintage_wall
"""

import argparse
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport
from backend.models.transaction import Transaction

logger = logging.getLogger(__name__)

# Tunable defaults — per Appendix D #17 these eventually live in
# assumption_sets so the Assumption Laboratory can override.
DEFAULT_HOLD_MIN_YEARS = 8
DEFAULT_HOLD_MEDIAN_YEARS = 10
DEFAULT_HOLD_MAX_YEARS = 12

# State filter: holdings come from acquisitions that actually happened
# (closed) or are imminent (signed). Counterfactuals are excluded.
HOLDING_STATES = {"closed", "signed"}


@dataclass
class FundHolding:
    """One fund-backed position derived from an acquisition transaction."""

    transaction_id: str
    airport_iata: str | None
    airport_name: str | None
    buyer_name: str
    fund_name: str | None
    fund_vintage: int
    transaction_close_year: int | None  # year position established
    stake_acquired_pct: float | None
    holding_age_years: float            # today - vintage
    expected_exit_year: int             # vintage + median hold
    expected_exit_window: list[int]     # [vintage + min, vintage + max]
    maturity_pct: float                 # 0-100; capped at 100


@dataclass
class MaturityWallBucket:
    """Count of holdings expected to exit in a given calendar year."""

    year: int
    count: int
    airports: list[str]
    holder_names: list[str]


def _to_year(d: date | None) -> int | None:
    return d.year if d is not None else None


def compute_holdings(
    db: Session,
    *,
    today: date | None = None,
    hold_min_years: int = DEFAULT_HOLD_MIN_YEARS,
    hold_median_years: int = DEFAULT_HOLD_MEDIAN_YEARS,
    hold_max_years: int = DEFAULT_HOLD_MAX_YEARS,
) -> list[FundHolding]:
    """
    Build the list of current fund-backed positions from acquisition
    transactions. One holding per (transaction, buyer-with-vintage) tuple —
    a consortium of 2 funds buying one airport yields 2 holdings.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()

    holdings: list[FundHolding] = []
    txns = db.scalars(
        select(Transaction).where(
            Transaction.state.in_(HOLDING_STATES),
            Transaction.transaction_type.in_({"acquisition", "minority_stake"}),
        )
    ).all()

    for txn in txns:
        airport = db.get(Airport, txn.airport_id) if txn.airport_id else None
        for buyer in (txn.buyer_entities or []):
            # Strategic operators don't exit on a vintage clock — skip.
            if buyer.get("is_strategic_operator") is True:
                continue
            vintage = buyer.get("fund_vintage")
            if not isinstance(vintage, int):
                continue
            holding_age = (today.year - vintage) + (today.month - 1) / 12.0
            expected_exit = vintage + hold_median_years
            window = [vintage + hold_min_years, vintage + hold_max_years]
            maturity_pct = min(100.0, max(0.0, holding_age / hold_median_years * 100))

            holdings.append(FundHolding(
                transaction_id=str(txn.id),
                airport_iata=airport.iata_code if airport else None,
                airport_name=airport.name if airport else None,
                buyer_name=buyer.get("name") or "<unknown>",
                fund_name=buyer.get("fund_name"),
                fund_vintage=vintage,
                transaction_close_year=_to_year(txn.close_date or txn.announce_date),
                stake_acquired_pct=buyer.get("equity_stake_pct"),
                holding_age_years=round(holding_age, 2),
                expected_exit_year=expected_exit,
                expected_exit_window=window,
                maturity_pct=round(maturity_pct, 1),
            ))

    return holdings


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
        b.holder_names.append(h.buyer_name)
    return sorted(buckets.values(), key=lambda b: b.year)


def methodology_notes(
    hold_min: int, hold_median: int, hold_max: int,
) -> list[str]:
    return [
        f"Hold period assumption: median {hold_median}y, range {hold_min}-{hold_max}y "
        "(typical for infrastructure funds; v1 default).",
        "Strategic operators (e.g. VINCI Airports, AENA Internacional) excluded — "
        "they don't exit on a vintage clock.",
        "Only transactions in state {closed, signed} feed this view. "
        "Counterfactual states (abandoned, pulled, etc.) are excluded.",
        "v1 limitation: divestments by a fund are NOT yet netted against "
        "their earlier acquisitions. A fund that bought into airport A and "
        "later sold its stake will still appear as a 'current' position. "
        "v2 should reconcile via the transactions table.",
        "Only buyers with explicit fund_vintage data appear. Transactions "
        "where the LLM couldn't extract vintage are silently omitted; "
        "absence here is not evidence of absence from the market.",
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
            print("  No holdings — no transactions in {closed,signed} with fund_vintage data.")
        for h in holdings:
            print(
                f"  {h.airport_iata or '?':>4} "
                f"{h.buyer_name[:30]:30s} "
                f"vintage={h.fund_vintage} "
                f"closed={h.transaction_close_year}  "
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
