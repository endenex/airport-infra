"""
Cross-source triangulation for numeric facts.

For each (airport, period_end, concept) where we have records from
multiple sources, write pairwise comparison rows into the
cross_validations table:

  - agreement       : True iff |Δ| / primary < AGREEMENT_THRESHOLD_PCT
  - discrepancy_pct : signed (comparison - primary) / primary * 100
  - flagged_for_review : True when discrepancy > FLAG_THRESHOLD_PCT
                         AND at least one side is an LLM-extracted record
                         (we trust structured-source disagreements less)

Source authority order (primary picked from the highest available):
  caa_uk > eurostat_aviation > llm:climateextractionpipeline > llm:operationalextractionpipeline
  > anything else.

Idempotent: re-running wipes prior cross_validations for the concept first
so a wider data set never leaves stale rows behind.

Run: uv run python -m analysis.cross_validation
     uv run python -m analysis.cross_validation --concept passengers_total
"""

import argparse
import logging
from collections import defaultdict
from datetime import date
from itertools import combinations
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import CrossValidation, DataRecord

logger = logging.getLogger(__name__)

# Source precedence: lower number = more authoritative. The most-authoritative
# source becomes the "primary" of each cross_validation pair.
SOURCE_AUTHORITY = {
    "caa_uk": 1,
    "eurostat_aviation": 2,
}
LLM_SOURCE_PREFIX = "llm:"

# Agreement when |Δ| ≤ 2% — small enough that rounding / period-edge effects
# don't trip it, large enough to absorb genuine but minor methodology drift.
AGREEMENT_THRESHOLD_PCT = 2.0

# Above this, we want a human to look at it (when an LLM is involved).
# Structured-source disagreements above this still get logged but don't
# auto-flag — they're more likely a real methodology difference than an
# extraction error.
FLAG_THRESHOLD_PCT = 5.0


def _source_priority(source_id: str) -> int:
    """Lower = more authoritative."""
    if source_id in SOURCE_AUTHORITY:
        return SOURCE_AUTHORITY[source_id]
    if source_id.startswith(LLM_SOURCE_PREFIX):
        return 100  # any LLM is less authoritative than any structured source
    return 50  # other structured sources we haven't ranked yet


def _is_llm(source_id: str) -> bool:
    return source_id.startswith(LLM_SOURCE_PREFIX)


def _get_value(record: DataRecord) -> float | None:
    raw = record.payload.get("value") if record.payload else None
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def cross_validate(
    db: Session,
    concept: str = "passengers_total",
    *,
    agreement_threshold_pct: float = AGREEMENT_THRESHOLD_PCT,
    flag_threshold_pct: float = FLAG_THRESHOLD_PCT,
) -> dict:
    """
    Run triangulation for one concept across all airports and periods.

    Returns a summary dict — counts of comparisons, agreements, flags, plus
    the most surprising disagreements (for logging).
    """
    # Pull every record for this concept that's linked to an airport.
    rows = db.scalars(
        select(DataRecord).where(
            DataRecord.airport_id.is_not(None),
            DataRecord.record_type == "OPERATIONAL",
        )
    ).all()

    # Group by (airport_id, period_end). Filter to the chosen concept.
    grouped: dict[tuple[Any, date], list[DataRecord]] = defaultdict(list)
    for r in rows:
        if (r.payload or {}).get("concept") != concept:
            continue
        if r.period_end is None or r.airport_id is None:
            continue
        grouped[(r.airport_id, r.period_end)].append(r)

    # Wipe prior cross_validations for this concept so a wider data set
    # doesn't leave stale pairs behind.
    db.execute(delete(CrossValidation).where(CrossValidation.field_name == concept))
    db.commit()

    total_groups = 0
    total_comparisons = 0
    total_agreements = 0
    total_flagged = 0
    biggest_disagreements: list[tuple[float, str, str, float, float]] = []

    for (airport_id, period_end), records in grouped.items():
        if len(records) < 2:
            continue
        total_groups += 1
        # Sort by authority — most-authoritative first
        records = sorted(records, key=lambda r: _source_priority(r.source_id))
        for primary, comparison in combinations(records, 2):
            # Within-source pairs aren't real cross-validations — they're
            # ingester edge cases (Basel-Mulhouse: FR_LFSB + CH_LFSB both
            # link to LFSB). Skip and let the ingester clean those up.
            if primary.source_id == comparison.source_id:
                continue
            p_val = _get_value(primary)
            c_val = _get_value(comparison)
            if p_val is None or c_val is None or p_val == 0:
                continue
            discrepancy_pct = (c_val - p_val) / p_val * 100
            abs_pct = abs(discrepancy_pct)
            agreement = abs_pct <= agreement_threshold_pct
            llm_involved = _is_llm(primary.source_id) or _is_llm(comparison.source_id)
            flagged = abs_pct > flag_threshold_pct and llm_involved

            db.add(CrossValidation(
                primary_record_id=primary.id,
                comparison_record_id=comparison.id,
                field_name=concept,
                primary_value={"value": p_val, "source_id": primary.source_id},
                comparison_value={"value": c_val, "source_id": comparison.source_id},
                agreement=agreement,
                discrepancy_pct=round(discrepancy_pct, 4),
                flagged_for_review=flagged,
            ))
            total_comparisons += 1
            if agreement:
                total_agreements += 1
            if flagged:
                total_flagged += 1
            biggest_disagreements.append((
                abs_pct, primary.source_id, comparison.source_id, p_val, c_val
            ))

    db.commit()

    # Surface the top 5 biggest disagreements regardless of flag status
    biggest_disagreements.sort(reverse=True)
    top = biggest_disagreements[:5]

    summary = {
        "concept": concept,
        "groups_with_multiple_sources": total_groups,
        "pairwise_comparisons": total_comparisons,
        "agreements": total_agreements,
        "flagged_for_review": total_flagged,
        "biggest_disagreements_pct": [
            {"pct": round(p, 2), "primary": ps, "comparison": cs,
             "primary_val": pv, "comparison_val": cv}
            for p, ps, cs, pv, cv in top
        ],
    }
    logger.info("Cross-validation %s: %s", concept, summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--concept", default="passengers_total")
    parser.add_argument("--agreement-pct", type=float, default=AGREEMENT_THRESHOLD_PCT)
    parser.add_argument("--flag-pct", type=float, default=FLAG_THRESHOLD_PCT)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        summary = cross_validate(
            db,
            concept=args.concept,
            agreement_threshold_pct=args.agreement_pct,
            flag_threshold_pct=args.flag_pct,
        )
        print(f"=== Cross-validation: {summary['concept']} ===")
        print(f"  groups_with_multiple_sources: {summary['groups_with_multiple_sources']}")
        print(f"  pairwise_comparisons:         {summary['pairwise_comparisons']}")
        print(f"  agreements (≤ threshold):     {summary['agreements']}")
        print(f"  flagged_for_review:           {summary['flagged_for_review']}")
        print()
        print("  Biggest disagreements:")
        for d in summary["biggest_disagreements_pct"]:
            print(
                f"    {d['pct']:>6.2f}%  {d['primary']:>25s}={d['primary_val']:>15,.0f}  "
                f"vs  {d['comparison']:>40s}={d['comparison_val']:>15,.0f}"
            )
    finally:
        db.close()
