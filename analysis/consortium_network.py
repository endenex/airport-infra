"""
Layer β.4 — Consortium Network Graph (Appendix D Layer β).

Builds an undirected graph of co-investment relationships from the
transactions table:

  - Nodes: distinct investor entities (named parties from buyer_entities,
    seller_entities, and continuing_holders).
  - Edges: two investors share an edge if they appear together in the
    same transaction on the same side (both buyers of the same deal,
    or both sellers). Edge weight = number of co-deals.

Used by the future Owner View / Deal Flow viewing modes per Appendix D
locked decision #18 — when GIP needs a partner for a new bid, historical
partners are more likely than random firms.

Methodology v1 limits:
  - "Co-investor" = appears on the same side of the same transaction.
    Doesn't yet detect parties that hold the same asset via separate
    transactions (e.g. one party bought in via a 2014 deal, another via
    a 2018 deal — they're co-investors today but not via shared
    transaction).
  - Strategic operators (is_strategic_operator=True) ARE included —
    consortium analysis cares about who partners with whom regardless
    of fund-vintage clock.
  - Rumored/suspected parties (identifier_status != "identified") are
    excluded from edges by default to avoid asserting partnerships the
    document didn't confirm.
"""

import argparse
import logging
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.holdings import compute_current_holdings
from backend.db.connection import SessionLocal
from backend.models.transaction import Transaction

logger = logging.getLogger(__name__)


@dataclass
class ConsortiumNode:
    """One investor in the graph."""

    name: str
    deal_count: int                 # transactions they appear in (any side)
    sides_seen: list[str]           # which roles they've played (buyer/seller/holder)
    is_strategic_operator: bool


@dataclass
class ConsortiumEdge:
    """A co-investment relationship between two investors."""

    party_a: str                    # sorted alphabetically for stable identity
    party_b: str
    weight: int                     # number of shared transactions
    sides: list[str]                # "buyer" / "seller" — which side they co-acted on
    transaction_ids: list[str]
    airport_iatas: list[str]        # airports where they've co-acted


Side = Literal["buyer", "seller"]


def _identified(entries: list[dict] | None) -> list[str]:
    """
    Extract names from a party-entries JSONB array, restricted to
    identifier_status='identified' so we never assert a rumoured
    partnership.
    """
    out: list[str] = []
    for entry in entries or []:
        name = entry.get("name")
        if not name:
            continue
        status = entry.get("identifier_status", "unknown")
        if status != "identified":
            continue
        out.append(name)
    return out


def compute_network(
    db: Session,
    *,
    include_unidentified: bool = False,
) -> tuple[list[ConsortiumNode], list[ConsortiumEdge]]:
    """
    Build (nodes, edges) from all transactions. Edges only form between
    parties on the SAME side of the same transaction (buyer-buyer pairs
    and seller-seller pairs). Counterfactual states (abandoned, pulled,
    rumored) ARE included — knowing who teamed up on a process even if
    it died is useful network signal.
    """
    edge_index: dict[tuple[str, str], dict] = {}
    node_deals: dict[str, set[str]] = defaultdict(set)
    node_sides: dict[str, set[str]] = defaultdict(set)
    node_strategic: dict[str, bool] = {}

    def _extract(entries: list[dict] | None) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        for entry in entries or []:
            name = entry.get("name")
            if not name:
                continue
            status = entry.get("identifier_status", "unknown")
            if status != "identified" and not include_unidentified:
                continue
            out.append((name, entry))
        return out

    txns = db.scalars(select(Transaction)).all()
    for txn in txns:
        airport_iata = None
        if txn.airport_id is not None:
            # Avoid an N+1 by accessing the relationship lazily; for ~10s of
            # txns this is acceptable. Replace with joinedload when needed.
            airport_iata = txn.airport.iata_code if txn.airport else None
        txn_id_str = str(txn.id)

        for side, entries in (("buyer", txn.buyer_entities),
                              ("seller", txn.seller_entities)):
            named = _extract(entries)
            for name, entry in named:
                node_deals[name].add(txn_id_str)
                node_sides[name].add(side)
                node_strategic[name] = bool(entry.get("is_strategic_operator", False))

            # Edges only between IDENTIFIED parties on the same side
            for (a, _), (b, _) in combinations(named, 2):
                # sorted() returns a list; cast to fixed-length tuple for mypy.
                ordered = sorted((a, b))
                key: tuple[str, str] = (ordered[0], ordered[1])
                if key not in edge_index:
                    edge_index[key] = {
                        "weight": 0, "sides": set(),
                        "transaction_ids": [], "airport_iatas": [],
                    }
                e = edge_index[key]
                e["weight"] += 1
                e["sides"].add(side)
                e["transaction_ids"].append(txn_id_str)
                if airport_iata:
                    e["airport_iatas"].append(airport_iata)

    nodes = [
        ConsortiumNode(
            name=name,
            deal_count=len(node_deals[name]),
            sides_seen=sorted(node_sides[name]),
            is_strategic_operator=node_strategic.get(name, False),
        )
        for name in sorted(node_deals)
    ]
    edges = [
        ConsortiumEdge(
            party_a=a, party_b=b,
            weight=v["weight"],
            sides=sorted(v["sides"]),
            transaction_ids=v["transaction_ids"],
            airport_iatas=sorted(set(v["airport_iatas"])),
        )
        for (a, b), v in sorted(edge_index.items(), key=lambda kv: -kv[1]["weight"])
    ]
    return nodes, edges


def methodology_notes() -> list[str]:
    return [
        "Co-investor = appears on the same side of the same transaction. "
        "Two parties holding the same asset via separate transactions are "
        "not linked here — see /capital-flows/co-ownership-network "
        "(holdings-based) for that case.",
        "Strategic operators (is_strategic_operator=True) ARE included — "
        "consortium analysis cares about partnerships regardless of fund "
        "vintage.",
        "Edges only form between parties whose identifier_status is "
        "'identified'. Rumoured or suspected parties never get asserted "
        "into the network. Pass include_unidentified=true to override "
        "(use sparingly — Layer γ honesty discipline).",
        "All transaction states feed the network — abandoned and pulled "
        "deals are signal too (who teamed up on a process even if it died).",
    ]


# ── Co-ownership network (holdings-based) ───────────────────────────────


@dataclass
class CoOwnershipEdge:
    """Two parties currently holding stakes in the same airport."""

    party_a: str
    party_b: str
    shared_airport_count: int
    shared_airports: list[str]           # IATA codes
    party_a_stake_pcts: list[float]      # parallel to shared_airports
    party_b_stake_pcts: list[float]      # parallel to shared_airports


def compute_co_ownership_network(
    db: Session,
    *,
    include_unidentified: bool = False,
) -> tuple[list[ConsortiumNode], list[CoOwnershipEdge]]:
    """
    Build the co-ownership graph from CURRENT holdings (reconciled from
    transactions via analysis.holdings). Two parties share an edge if they
    both currently hold a position in the same airport, regardless of
    whether they got there via the same transaction or separate ones.

    This is the "fix" for the β.4 gap surfaced by the user: when Fund A
    buys 50% of Airport X in 2018 and Fund B buys 30% of Airport X in
    2022, our transaction-based network shows no edge between them
    (different deals). Holdings-based view shows the edge because they
    currently both hold positions in X.
    """
    holdings = compute_current_holdings(
        db, include_unidentified=include_unidentified
    )
    # Index: airport_id → list of holdings
    by_airport: dict = defaultdict(list)
    for h in holdings:
        by_airport[h.airport_id].append(h)

    # Build nodes (one per distinct holder)
    node_data: dict[str, dict] = {}
    for h in holdings:
        n = node_data.setdefault(h.holder_name, {
            "airports": set(), "is_strategic_operator": False,
        })
        if h.airport_iata:
            n["airports"].add(h.airport_iata)
        n["is_strategic_operator"] = n["is_strategic_operator"] or h.is_strategic_operator

    nodes = [
        ConsortiumNode(
            name=name,
            deal_count=len(d["airports"]),  # repurpose: airports held, not deals
            sides_seen=["holder"],
            is_strategic_operator=d["is_strategic_operator"],
        )
        for name, d in sorted(node_data.items())
    ]

    # Build co-ownership edges
    edge_index: dict[tuple[str, str], CoOwnershipEdge] = {}
    for _airport_id, hs in by_airport.items():
        if len(hs) < 2:
            continue
        for h_a, h_b in combinations(hs, 2):
            a, b = sorted([h_a.holder_name, h_b.holder_name])
            if a == b:
                continue
            stake_a = h_a.current_stake_pct if h_a.holder_name == a else h_b.current_stake_pct
            stake_b = h_b.current_stake_pct if h_b.holder_name == b else h_a.current_stake_pct
            iata = h_a.airport_iata or h_b.airport_iata or "?"
            key = (a, b)
            if key in edge_index:
                e = edge_index[key]
                e.shared_airport_count += 1
                e.shared_airports.append(iata)
                e.party_a_stake_pcts.append(stake_a)
                e.party_b_stake_pcts.append(stake_b)
            else:
                edge_index[key] = CoOwnershipEdge(
                    party_a=a, party_b=b,
                    shared_airport_count=1,
                    shared_airports=[iata],
                    party_a_stake_pcts=[stake_a],
                    party_b_stake_pcts=[stake_b],
                )

    edges = sorted(edge_index.values(), key=lambda e: -e.shared_airport_count)
    return nodes, edges


def co_ownership_methodology_notes() -> list[str]:
    return [
        "Edges form between any two parties who CURRENTLY hold positions "
        "in the same airport — even if they got there via separate "
        "transactions years apart.",
        "Holdings are reconciled from CLOSED transactions (see "
        "analysis/holdings.py). Signed-but-not-closed deals are not yet "
        "reflected.",
        "Edge weight = number of airports where the pair both hold. "
        "Stakes are parallel arrays — party_a_stake_pcts[i] is party_a's "
        "stake in shared_airports[i].",
        "Identifier-status discipline: rumoured/suspected parties "
        "excluded by default (Layer γ).",
        "v1 limitation: gross stake math inherited from holdings — see "
        "analysis/holdings.py methodology notes.",
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
        nodes, edges = compute_network(
            db, include_unidentified=args.include_unidentified
        )

        print(f"\n=== Consortium network ({len(nodes)} investors, {len(edges)} edges) ===\n")
        print("Top investors by deal count:")
        for n in sorted(nodes, key=lambda x: -x.deal_count)[:15]:
            badge = " [strategic]" if n.is_strategic_operator else ""
            print(f"  {n.name:40s}  deals={n.deal_count}  sides={n.sides_seen}{badge}")

        print("\nTop co-investment edges:")
        for e in edges[:15]:
            airports = ",".join(e.airport_iatas) if e.airport_iatas else "—"
            print(
                f"  {e.party_a[:30]:30s}  ↔  {e.party_b[:30]:30s}  "
                f"deals={e.weight} sides={e.sides} airports={airports}"
            )

        print("\nMethodology notes:")
        for note in methodology_notes():
            print(f"  - {note}")
    finally:
        db.close()
