"""
Current ownership holdings reconciled from the transactions table.

Replays all CLOSED transactions chronologically per airport:
  - buyer_entities: add their stake to the holder's position
  - seller_entities: subtract their stake (close position if reaches 0)
  - continuing_holders: seed position if not yet seen (their first
    appearance gives us a pre-existing-position floor)

Result: a current-snapshot view {(airport_id, holder_name) → Holding} that
both β.1 (vintage maturity wall, needs to know who CURRENTLY holds vs who
once bought) and β.4 (consortium network, needs to detect co-holdings even
when established via separate transactions) consume.

Methodology v1 limits:
  - Only CLOSED transactions count toward holdings. Signed-but-not-closed
    deals are accumulated separately (`signed_pipeline`).
  - Stake percentages from buyer_entities are taken as the AMOUNT
    ACQUIRED in that transaction (per the v1.1 transaction prompt's
    stake-change rule), not the resulting total. Same for sellers.
  - continuing_holders seed positions: the FIRST time we see a continuing
    holder for an airport, their post_transaction_stake_pct becomes their
    holding floor. This handles pre-transaction-data airports honestly —
    we know they held this much at this point in time.
  - Rumoured / suspected parties (identifier_status != "identified") are
    excluded by default — Layer γ honesty discipline. They never appear
    as current holders.
  - Stakes are tracked separately by `fund_name` if available, otherwise
    by holder name. (Two different funds of the same manager → distinct
    positions.)
"""

import argparse
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport
from backend.models.transaction import Transaction

logger = logging.getLogger(__name__)


@dataclass
class HoldingEvent:
    """One transaction's contribution to a holding."""

    transaction_id: str
    when: date | None
    side: str  # "buyer" | "seller" | "continuing_holder"
    stake_delta_pct: float  # signed: positive = added, negative = sold, 0 = seeded
    new_total_pct: float


@dataclass
class Holding:
    """One party's current position in one airport."""

    airport_id: object
    airport_iata: str | None
    airport_name: str | None
    holder_name: str
    fund_name: str | None
    fund_vintage: int | None
    is_strategic_operator: bool
    current_stake_pct: float
    established_via: list[HoldingEvent] = field(default_factory=list)
    first_established: date | None = None
    last_changed: date | None = None
    sources_seen: set[str] = field(default_factory=set)


def _position_key(party: dict) -> tuple[str, str | None]:
    """
    A position is identified by (name, fund_name) so different funds of the
    same manager are tracked separately. For strategic operators with no
    fund_name, key is just (name, None).
    """
    return (party.get("name") or "<unknown>", party.get("fund_name"))


def _stake_or_zero(party: dict, field_name: str = "equity_stake_pct") -> float:
    v = party.get(field_name)
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _txn_date(t: Transaction) -> date | None:
    """For chronological replay, prefer close_date, then signing, then announce."""
    return t.close_date or t.signing_date or t.announce_date


def compute_current_holdings(
    db: Session,
    *,
    include_unidentified: bool = False,
) -> list[Holding]:
    """
    Replay all CLOSED transactions to derive current per-(airport, holder)
    positions. Returns positions where stake > 0.
    """
    # Only equity-changing transaction types affect holdings. Refinancings
    # are debt events, not ownership changes; "other" is too ambiguous to
    # safely process.
    OWNERSHIP_TRANSACTION_TYPES = {  # noqa: N806
        "acquisition", "divestment", "minority_stake",
        "secondary_buyout", "ipo", "concession_award",
    }
    txns = db.scalars(
        select(Transaction).where(
            Transaction.state == "closed",
            Transaction.transaction_type.in_(OWNERSHIP_TRANSACTION_TYPES),
        )
    ).all()
    # Group by airport_id; sort by date so replay order is chronological.
    by_airport: dict[object, list[Transaction]] = defaultdict(list)
    for t in txns:
        if t.airport_id is None:
            continue
        by_airport[t.airport_id].append(t)
    for tlist in by_airport.values():
        tlist.sort(key=lambda x: _txn_date(x) or date.min)

    # Two-level state: per airport, then per (holder_name, fund_name)
    holdings: dict[object, dict[tuple[str, str | None], Holding]] = defaultdict(dict)
    airport_cache: dict = {}

    def _airport(airport_id) -> Airport | None:
        if airport_id not in airport_cache:
            airport_cache[airport_id] = db.get(Airport, airport_id)
        return airport_cache[airport_id]

    def _identified(party: dict) -> bool:
        return (
            party.get("identifier_status", "unknown") == "identified"
            or include_unidentified
        )

    def _get_or_create_holding(
        airport_id, party: dict
    ) -> Holding:
        key = _position_key(party)
        if key in holdings[airport_id]:
            return holdings[airport_id][key]
        airport = _airport(airport_id)
        h = Holding(
            airport_id=airport_id,
            airport_iata=airport.iata_code if airport else None,
            airport_name=airport.name if airport else None,
            holder_name=party.get("name") or "<unknown>",
            fund_name=party.get("fund_name"),
            fund_vintage=party.get("fund_vintage") if isinstance(
                party.get("fund_vintage"), int) else None,
            is_strategic_operator=bool(party.get("is_strategic_operator", False)),
            current_stake_pct=0.0,
        )
        holdings[airport_id][key] = h
        return h

    for airport_id, tlist in by_airport.items():
        for txn in tlist:
            when = _txn_date(txn)
            txn_id = str(txn.id)

            # continuing_holders SEED first (they were already there before
            # this transaction). Only seed if we haven't seen them yet.
            for party in (txn.continuing_holders or []):
                if not _identified(party):
                    continue
                key = _position_key(party)
                if key in holdings[airport_id]:
                    continue  # already tracked from a prior transaction
                h = _get_or_create_holding(airport_id, party)
                seed_pct = _stake_or_zero(party, "post_transaction_stake_pct")
                h.current_stake_pct = seed_pct
                h.first_established = when
                h.last_changed = when
                h.sources_seen.add("continuing_holder")
                h.established_via.append(HoldingEvent(
                    transaction_id=txn_id, when=when,
                    side="continuing_holder",
                    stake_delta_pct=0.0,
                    new_total_pct=h.current_stake_pct,
                ))

            # Buyers ADD their acquired stake
            for party in (txn.buyer_entities or []):
                if not _identified(party):
                    continue
                h = _get_or_create_holding(airport_id, party)
                delta = _stake_or_zero(party)
                h.current_stake_pct += delta
                if h.first_established is None:
                    h.first_established = when
                h.last_changed = when
                h.sources_seen.add("buyer")
                h.established_via.append(HoldingEvent(
                    transaction_id=txn_id, when=when, side="buyer",
                    stake_delta_pct=delta,
                    new_total_pct=h.current_stake_pct,
                ))

            # Sellers SUBTRACT their sold stake
            for party in (txn.seller_entities or []):
                if not _identified(party):
                    continue
                h = _get_or_create_holding(airport_id, party)
                delta = _stake_or_zero(party)
                h.current_stake_pct -= delta
                h.last_changed = when
                h.sources_seen.add("seller")
                h.established_via.append(HoldingEvent(
                    transaction_id=txn_id, when=when, side="seller",
                    stake_delta_pct=-delta,
                    new_total_pct=h.current_stake_pct,
                ))

    # Flatten + filter to positions with positive current stake.
    out: list[Holding] = []
    for airport_id, by_key in holdings.items():
        for h in by_key.values():
            if h.current_stake_pct > 0:
                out.append(h)
    out.sort(key=lambda h: (h.airport_iata or "", -h.current_stake_pct))
    return out


def holdings_by_airport(
    holdings: list[Holding],
) -> dict[object, list[Holding]]:
    """Group holdings list by airport_id for per-airport rollups."""
    out: dict[object, list[Holding]] = defaultdict(list)
    for h in holdings:
        out[h.airport_id].append(h)
    return out


@dataclass
class StakeReconciliation:
    """Per-airport sanity check on whether reconciled stakes sum to 100%."""

    airport_iata: str | None
    airport_name: str | None
    total_held_pct: float
    holder_count: int
    deviation_from_100_pct: float  # signed: negative = under, positive = over
    status: str                     # "balanced" | "under_allocated" | "over_allocated"


DEFAULT_RECONCILIATION_TOLERANCE_PCT = 1.0


def reconcile_stakes(
    holdings: list[Holding],
    *,
    tolerance_pct: float = DEFAULT_RECONCILIATION_TOLERANCE_PCT,
) -> list[StakeReconciliation]:
    """
    For each airport, check whether the sum of current holder stakes is
    close to 100%. Under-allocated airports have transaction-data gaps
    (likely missing continuing holders or pre-existing positions).
    Over-allocated airports point to extraction errors (LLM double-counted
    a party, or a stake field is wrong).

    This is a data-quality signal, not a hard constraint — many airports
    in our dataset are under-allocated simply because we haven't ingested
    every transaction in their history. Surfacing the deviation gives a
    reviewer the right place to focus.
    """
    by_airport: dict[object, list[Holding]] = defaultdict(list)
    for h in holdings:
        by_airport[h.airport_id].append(h)

    out: list[StakeReconciliation] = []
    for _airport_id, hs in by_airport.items():
        total = sum(h.current_stake_pct for h in hs)
        deviation = total - 100.0
        if abs(deviation) <= tolerance_pct:
            status = "balanced"
        elif deviation > 0:
            status = "over_allocated"
        else:
            status = "under_allocated"
        out.append(StakeReconciliation(
            airport_iata=hs[0].airport_iata,
            airport_name=hs[0].airport_name,
            total_held_pct=round(total, 2),
            holder_count=len(hs),
            deviation_from_100_pct=round(deviation, 2),
            status=status,
        ))
    # Most-deviated first — reviewer's natural sort order.
    out.sort(key=lambda r: -abs(r.deviation_from_100_pct))
    return out


def methodology_notes() -> list[str]:
    return [
        "Only CLOSED transactions feed holdings. signed / abandoned / pulled "
        "/ rumored states are not yet reflected — those go through "
        "/transactions for case-by-case review.",
        "Stake percentages from buyer_entities are the amount ACQUIRED in "
        "that transaction (per transaction-prompt v1.1 stake-change rule), "
        "not the resulting total holding.",
        "continuing_holders seed positions on first appearance — their "
        "post_transaction_stake_pct gives a floor for parties who held "
        "before our transaction record begins.",
        "Positions are keyed by (holder_name, fund_name) so different funds "
        "of the same manager (e.g. MIP III vs MIP IV) are tracked separately.",
        "Identifier-status discipline: rumoured/suspected parties are "
        "excluded by default. Pass include_unidentified=true for exploratory "
        "queries (Layer γ honesty discipline).",
        "v1 limitation: gross stake math. We don't normalise to 100% per "
        "airport, so under-/over-counted residual positions are possible "
        "where the underlying transaction data has gaps.",
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--include-unidentified", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        holdings = compute_current_holdings(
            db, include_unidentified=args.include_unidentified
        )
        print(f"\n=== Current holdings ({len(holdings)} positions) ===\n")
        for h in holdings:
            badge = " [strategic]" if h.is_strategic_operator else ""
            fund = f" ({h.fund_name})" if h.fund_name else ""
            print(
                f"  {h.airport_iata or '?':>4} "
                f"{h.holder_name + fund:50.50s} "
                f"stake={h.current_stake_pct:5.2f}%  "
                f"sources={sorted(h.sources_seen)}{badge}"
            )
        print("\nMethodology notes:")
        for note in methodology_notes():
            print(f"  - {note}")
    finally:
        db.close()
