"""
Anomalies endpoint — Appendix D Layer δ.

Surfaces pattern-break detection over the operational time series we
already have. Per locked decision #20, this layer runs in shadow mode
in v1 — flags are returned to enable founder review but the language
discipline is enforced from the API outward: no prediction copy, only
detection copy. The UI-copy linter test (tests/test_anomaly_ui_copy.py)
scans this file and the analysis module for forbidden words.
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from analysis.anomaly_detection import (
    DEFAULT_MIN_HISTORICAL_YEARS,
    DEFAULT_Z_THRESHOLD,
    OPERATIONAL_CONCEPTS_IN_SCOPE,
    detect_operational_pattern_breaks,
    methodology_notes,
)
from backend.db.connection import get_db

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get(
    "/operational",
    summary="Layer δ.2 — Operational pattern breaks (shadow mode)",
    description=(
        "Pattern-break flags from the operational time series. Detection "
        "only — silence means no flag, not 'all clear'. Each flag carries "
        "a z-score, the historical baseline, and the source IDs that "
        "contributed, so a reviewer can trace any flag back to its data. "
        "Returns ALL flags in v1; downstream consumers decide which to "
        "surface to customers based on per-flag-type review."
    ),
)
def operational_anomalies(
    db: Session = Depends(get_db),
    z_threshold: float = Query(DEFAULT_Z_THRESHOLD, ge=0.5, le=10),
    min_historical_years: int = Query(DEFAULT_MIN_HISTORICAL_YEARS, ge=2, le=20),
    concept: str | None = Query(None, description=f"Filter to one of: {sorted(OPERATIONAL_CONCEPTS_IN_SCOPE)}"),
) -> dict:
    flags = detect_operational_pattern_breaks(
        db,
        z_threshold=z_threshold,
        min_historical_years=min_historical_years,
    )
    if concept:
        flags = [f for f in flags if f.concept == concept]
    return {
        "flags": [asdict(f) for f in flags],
        "thresholds": {
            "z_threshold": z_threshold,
            "min_historical_years": min_historical_years,
        },
        "concepts_in_scope": sorted(OPERATIONAL_CONCEPTS_IN_SCOPE),
        "shadow_mode": True,
        "methodology_notes": methodology_notes(),
    }
