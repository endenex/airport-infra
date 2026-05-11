"""
Capital Flows endpoints — Appendix D Layer β.

Per Appendix D locked decision #18, Capital Flows is NOT a separate UI
surface. It's a viewing mode within Owner View and Deal Flow View. This
router exposes the underlying data for those future viewing modes; the
frontend mounts it inside the relevant surface, not as a standalone tab.

Sub-views supported here:
  - β.1 fund vintage maturity wall  →  GET /capital-flows/fund-vintage-wall
  - β.2 LP commitment shifts        →  (future)
  - β.3 strategic operator patterns →  (future)
  - β.4 consortium network          →  (future)
  - β.5 credit appetite             →  (future)
"""

from dataclasses import asdict
from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from analysis.consortium_network import (
    compute_network,
)
from analysis.consortium_network import (
    methodology_notes as consortium_notes,
)
from analysis.fund_vintage_wall import (
    DEFAULT_HOLD_MAX_YEARS,
    DEFAULT_HOLD_MEDIAN_YEARS,
    DEFAULT_HOLD_MIN_YEARS,
    aggregate_by_exit_year,
    compute_holdings,
    methodology_notes,
)
from backend.db.connection import get_db

router = APIRouter(prefix="/capital-flows", tags=["capital-flows"])


@router.get(
    "/consortium-network",
    summary="Layer β.4 — Co-investment network graph",
    description=(
        "Nodes are distinct named investors; edges form when two parties "
        "appear together on the same side of the same transaction. "
        "Edges only form between identifier_status='identified' parties — "
        "rumoured partnerships never asserted (Layer γ honesty discipline). "
        "Set include_unidentified=true to override (use sparingly)."
    ),
)
def consortium_network(
    db: Session = Depends(get_db),
    include_unidentified: bool = Query(
        False,
        description="Include parties with identifier_status != 'identified'. Off by default.",
    ),
) -> dict:
    nodes, edges = compute_network(db, include_unidentified=include_unidentified)
    return {
        "nodes": [asdict(n) for n in nodes],
        "edges": [asdict(e) for e in edges],
        "methodology_notes": consortium_notes(),
    }


@router.get(
    "/fund-vintage-wall",
    summary="Layer β.1 — Fund vintage maturity wall",
    description=(
        "Per-position holding metadata derived from acquisitions, plus a "
        "maturity-wall aggregation by expected exit year. Methodology "
        "notes travel with the response so consumers can defend any "
        "downstream chart against the underlying assumptions."
    ),
)
def fund_vintage_wall(
    db: Session = Depends(get_db),
    today: date_type | None = Query(
        None,
        description="Override 'today' (YYYY-MM-DD). Useful for back-testing.",
    ),
    hold_min_years: int = Query(DEFAULT_HOLD_MIN_YEARS, ge=1, le=30),
    hold_median_years: int = Query(DEFAULT_HOLD_MEDIAN_YEARS, ge=1, le=30),
    hold_max_years: int = Query(DEFAULT_HOLD_MAX_YEARS, ge=1, le=30),
) -> dict:
    holdings = compute_holdings(
        db, today=today,
        hold_min_years=hold_min_years,
        hold_median_years=hold_median_years,
        hold_max_years=hold_max_years,
    )
    buckets = aggregate_by_exit_year(holdings)
    return {
        "holdings": [asdict(h) for h in holdings],
        "by_exit_year": [asdict(b) for b in buckets],
        "assumptions": {
            "hold_min_years": hold_min_years,
            "hold_median_years": hold_median_years,
            "hold_max_years": hold_max_years,
        },
        "methodology_notes": methodology_notes(
            hold_min_years, hold_median_years, hold_max_years,
        ),
    }
