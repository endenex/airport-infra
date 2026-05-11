"""
Layer δ.2 — Operational Pattern Breaks (Appendix D Layer δ).

For each (airport, concept), compare the most recent year's value to the
historical baseline of preceding years. Flag when the absolute z-score
exceeds the threshold and ≥ min_historical_years of history exists.

CRITICAL FRAMING DISCIPLINE (Appendix D locked decision #20).
This layer surfaces FLAGS for human review, NEVER predictions. UI copy,
API docstrings, and methodology notes must use:
  ✓ "pattern detected"
  ✓ "deviation observed"
  ✓ "worth attention"
  ✓ "flagged"
NEVER:
  ✗ "expect", "predict", "will", "forecast"
  ✗ "imminent", "indicates", "warns"

A UI-copy linter test (tests/test_anomaly_ui_copy.py) scans this module
and the router for the forbidden words. The discipline is enforced
mechanically, not by reviewer attention alone.

Shadow mode: v1 always returns the full flag set. Downstream consumers
decide whether to surface to customers. Per the appendix, customer-facing
exposure is gated until false-positive rates are characterised — that
happens later, not in this prototype.

Data scope:
  - record_type = 'OPERATIONAL'
  - concept ∈ {'passengers_total', 'air_transport_movements', 'cargo_tonnes'}
  - Annual values only (period_end = YYYY-12-31)
  - Source-agnostic: CAA + Eurostat + LLM-PDF all feed the same baseline.
"""

import argparse
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport, DataRecord

logger = logging.getLogger(__name__)

# Concepts where year-over-year baselines are sensible. Net-zero target
# year and other one-shot concepts don't belong here.
OPERATIONAL_CONCEPTS_IN_SCOPE = {
    "passengers_total",
    "air_transport_movements",
    "cargo_tonnes",
}

DEFAULT_Z_THRESHOLD = 2.0
DEFAULT_MIN_HISTORICAL_YEARS = 3


@dataclass
class OperationalFlag:
    """One detected pattern break — pure detection signal, no inference."""

    airport_iata: str | None
    airport_name: str | None
    concept: str
    period_end: date
    observed_value: float
    historical_mean: float
    historical_stddev: float
    z_score: float                 # signed: positive = above baseline
    historical_years: list[int]
    source_ids: list[str]          # which sources contributed (for traceability)


def _value(record: DataRecord) -> float | None:
    payload = record.payload or {}
    raw = payload.get("value")
    if raw is None:
        return None
    try:
        return float(raw) if not isinstance(raw, Decimal) else float(raw)
    except (TypeError, ValueError):
        return None


def detect_operational_pattern_breaks(
    db: Session,
    *,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    min_historical_years: int = DEFAULT_MIN_HISTORICAL_YEARS,
) -> list[OperationalFlag]:
    """
    Detect deviations from historical baseline. Returns one flag per
    (airport, concept) where the latest year deviates > z_threshold σ
    from the mean of preceding years.

    No projection, no prediction — only detection of what already happened
    relative to recorded history.
    """
    records = db.scalars(
        select(DataRecord).where(
            DataRecord.record_type == "OPERATIONAL",
            DataRecord.airport_id.is_not(None),
            DataRecord.period_end.is_not(None),
        )
    ).all()

    # Group: (airport_id, concept) → {year → [(value, source_id)]}
    grouped: dict[tuple, dict[int, list[tuple[float, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in records:
        payload = r.payload or {}
        concept = payload.get("concept")
        if concept not in OPERATIONAL_CONCEPTS_IN_SCOPE:
            continue
        # Annual values only — period_end on Dec 31
        if r.period_end is None or r.period_end.month != 12 or r.period_end.day != 31:
            continue
        v = _value(r)
        if v is None or v <= 0:
            continue
        grouped[(r.airport_id, concept)][r.period_end.year].append((v, r.source_id))

    flags: list[OperationalFlag] = []
    airport_cache: dict = {}

    for (airport_id, concept), year_map in grouped.items():
        if len(year_map) < min_historical_years + 1:
            # Need ≥ min_historical_years of history + 1 latest year to compare
            continue
        years = sorted(year_map.keys())
        latest_year = years[-1]
        history_years = years[:-1]

        # When multiple sources report the same year, use the mean
        def mean_value(year: int) -> float:
            vals = [v for v, _ in year_map[year]]
            return sum(vals) / len(vals)

        latest_value = mean_value(latest_year)
        historical_values = [mean_value(y) for y in history_years]

        h_mean = sum(historical_values) / len(historical_values)
        # Sample standard deviation (n-1) — Bessel's correction
        if len(historical_values) >= 2:
            variance = sum((v - h_mean) ** 2 for v in historical_values) / (
                len(historical_values) - 1
            )
            h_stddev = math.sqrt(variance)
        else:
            h_stddev = 0.0

        if h_stddev == 0:
            # No historical variance — can't z-score. Skip rather than
            # divide by zero or assert any pattern.
            continue

        z = (latest_value - h_mean) / h_stddev
        if abs(z) < z_threshold:
            continue

        airport = airport_cache.get(airport_id)
        if airport is None:
            airport = db.get(Airport, airport_id)
            airport_cache[airport_id] = airport

        source_ids: list[str] = sorted(
            {sid for y in years for _, sid in year_map[y]}
        )

        flags.append(OperationalFlag(
            airport_iata=airport.iata_code if airport else None,
            airport_name=airport.name if airport else None,
            concept=concept,
            period_end=date(latest_year, 12, 31),
            observed_value=round(latest_value, 2),
            historical_mean=round(h_mean, 2),
            historical_stddev=round(h_stddev, 2),
            z_score=round(z, 3),
            historical_years=history_years,
            source_ids=source_ids,
        ))

    # Order by absolute z-score so the most-deviated flags come first.
    flags.sort(key=lambda f: -abs(f.z_score))
    return flags


def methodology_notes() -> list[str]:
    """
    Plain-language disclosures that travel with every API response.

    UI-copy discipline: this text is user-facing. The linter test scans
    these notes for forbidden words. Edit carefully.
    """
    return [
        "Detection only — pattern detected vs historical baseline. No "
        "projection of future values, no inference of cause.",
        "Annual values only. Each year's value is the cross-source mean "
        "where multiple sources (CAA, Eurostat, LLM-PDF) report the same "
        "airport-year.",
        "Baseline = preceding years (at least 3 needed). The latest year "
        "is compared to the mean ± sample standard deviation of prior "
        "years. Pattern detected when |z| > threshold (default 2.0).",
        "Airports with zero historical variance are skipped — z-score is "
        "undefined, no flag is asserted.",
        "Shadow mode: v1 surfaces ALL flags. Customer-facing exposure is "
        "gated on per-flag-type false-positive characterisation, not in "
        "this prototype.",
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--z-threshold", type=float, default=DEFAULT_Z_THRESHOLD)
    parser.add_argument("--min-history", type=int, default=DEFAULT_MIN_HISTORICAL_YEARS)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        flags = detect_operational_pattern_breaks(
            db,
            z_threshold=args.z_threshold,
            min_historical_years=args.min_history,
        )
        print(f"\n=== Operational pattern breaks ({len(flags)} flagged) ===\n")
        if not flags:
            print("  No patterns deviating beyond threshold. "
                  "(This is detection-only — silence means no flag, not 'all clear'.)")
        for f in flags[:30]:
            direction = "↑" if f.z_score > 0 else "↓"
            print(
                f"  {f.airport_iata or '?':>4} {f.concept:25s} "
                f"{f.period_end} {direction} "
                f"z={f.z_score:+.2f}  observed={f.observed_value:>15,.0f}  "
                f"baseline={f.historical_mean:>15,.0f}±{f.historical_stddev:,.0f} "
                f"over {f.historical_years[0]}-{f.historical_years[-1]}"
            )
        print("\nMethodology notes (also returned via API):")
        for note in methodology_notes():
            print(f"  - {note}")
    finally:
        db.close()
