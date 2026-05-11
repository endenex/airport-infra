"""
Layer α — Concession Lifecycle Position calculator (Appendix D).

Computes lifecycle stage (early / mid / late / indeterminate) per airport
from CONCESSION + FINANCIAL inputs, stamps the airport row with stage,
methodology version, inputs JSONB, and computed_at.

Methodology v1.1.0 thresholds:
  Late-stage triggers (any):
    - concession_horizon_remaining_pct < 30
    - debt_amortisation_pct > 70
  Early-stage (all three required):
    - capex_programme_completion_pct < 30
    - debt_amortisation_pct < 20
    - concession_horizon_remaining_pct > 70
  Mid-stage: capex_programme_completion_pct in [30, 70]
  Indeterminate: insufficient inputs

For continuously-regulated airports, the current regulatory period is
used as a proxy for "concession period." This assumption is recorded in
lifecycle_inputs.methodology_notes so it travels with every classification.

Idempotent — re-running overwrites the previous classification on each
airport (and the methodology_version_id captures which run produced it).

Run: uv run python -m analysis.lifecycle_position
     uv run python -m analysis.lifecycle_position --iata LHR
"""

import argparse
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport, DataRecord, MethodologyVersion

logger = logging.getLogger(__name__)

METHODOLOGY_VERSION_STRING = "1.1.0"


# ── Inputs and outputs ──────────────────────────────────────────────────


@dataclass
class LifecycleInputs:
    """
    Inputs to the lifecycle classification. Each percent field is 0-100;
    None means the input is unavailable from current data sources.
    """

    concession_horizon_remaining_pct: float | None = None
    capex_programme_completion_pct: float | None = None
    debt_amortisation_pct: float | None = None
    dividend_extraction_pct: float | None = None
    years_since_concession_award: float | None = None
    # IDs of DataRecords used in the computation. Provenance trail so a
    # downstream caller can audit the classification.
    source_record_ids: list[str] = field(default_factory=list)
    # Free-text annotations for assumptions and limitations, e.g.
    # "regulated airport — H7 period used as concession proxy".
    methodology_notes: list[str] = field(default_factory=list)


@dataclass
class ComputedPosition:
    stage: str  # "early" | "mid" | "late" | "indeterminate"
    rationale: str  # Which threshold rule fired, for audit / UI tooltip
    methodology_version: str
    inputs: LifecycleInputs


# ── Classification logic ─────────────────────────────────────────────────


def classify(inputs: LifecycleInputs) -> tuple[str, str]:
    """
    Apply Methodology v1.1.0 thresholds. Returns (stage, rationale).

    Late-stage triggers checked first (worst-case wins) — an airport whose
    horizon is < 30% is late-stage regardless of its capex profile, because
    the horizon dominates the analytical questions that matter for it.
    """
    horizon = inputs.concession_horizon_remaining_pct
    capex = inputs.capex_programme_completion_pct
    debt = inputs.debt_amortisation_pct

    # Late-stage: any trigger fires
    if horizon is not None and horizon < 30:
        return "late", f"concession_horizon_remaining {horizon:.1f}% < 30%"
    if debt is not None and debt > 70:
        return "late", f"debt_amortisation {debt:.1f}% > 70%"

    # Early-stage: requires all three signals, with debt explicitly low
    if (
        capex is not None and capex < 30
        and debt is not None and debt < 20
        and horizon is not None and horizon > 70
    ):
        return (
            "early",
            f"capex {capex:.1f}% < 30% AND debt {debt:.1f}% < 20% "
            f"AND horizon {horizon:.1f}% > 70%",
        )

    # Mid-stage: capex sits in the 30-70 band (steady-state operation
    # evidenced by capex programme being substantially deployed but not yet
    # winding down).
    if capex is not None and 30 <= capex <= 70:
        return "mid", f"capex_programme_completion {capex:.1f}% in [30%, 70%]"

    return "indeterminate", "insufficient inputs to apply v1.1.0 thresholds"


# ── Input extraction from CONCESSION records ─────────────────────────────


def compute_inputs(
    db: Session,
    airport: Airport,
    today: date,
) -> LifecycleInputs:
    """
    Gather lifecycle inputs for one airport from the records we have.

    For v1 this only pulls from CONCESSION records (regulatory period bounds,
    capex allowance, annual capex forecast). Debt amortisation and dividend
    trajectory inputs are left null until we ingest financial-statement data.
    """
    inputs = LifecycleInputs(source_record_ids=[], methodology_notes=[])

    # Pull all CONCESSION records for this airport, scoped to one framework.
    # If the airport has multiple regulatory frameworks (e.g. AENA's DORA I
    # and DORA II), prefer the most recent one whose period covers today.
    concession_records = db.scalars(
        select(DataRecord).where(
            DataRecord.airport_id == airport.id,
            DataRecord.record_type == "CONCESSION",
        )
    ).all()

    if not concession_records:
        inputs.methodology_notes.append(
            "no CONCESSION records available — debt/dividend inputs also unavailable"
        )
        return inputs

    # Pick a framework: the one whose period covers `today`, falling back to
    # the most recent.
    frameworks: dict[str, dict[str, Any]] = {}
    for r in concession_records:
        fw = (r.payload or {}).get("regulatory_framework_name")
        if not fw:
            continue
        if fw not in frameworks:
            frameworks[fw] = {
                "period_start": r.period_start,
                "period_end": r.period_end,
                "records": [],
            }
        frameworks[fw]["records"].append(r)
        # Tighten the period bounds — record-level periods can be annual,
        # but we want the framework's *outer* bounds.
        if r.period_start and frameworks[fw]["period_start"]:
            frameworks[fw]["period_start"] = min(
                frameworks[fw]["period_start"], r.period_start
            )
        if r.period_end and frameworks[fw]["period_end"]:
            frameworks[fw]["period_end"] = max(
                frameworks[fw]["period_end"], r.period_end
            )

    if not frameworks:
        inputs.methodology_notes.append("CONCESSION records lack regulatory_framework_name")
        return inputs

    # Choose active framework (period covers today). Fall back to most recent.
    active_name = None
    for name, fw in frameworks.items():
        if (fw["period_start"] and fw["period_end"]
                and fw["period_start"] <= today <= fw["period_end"]):
            active_name = name
            break
    if active_name is None:
        active_name = max(
            frameworks, key=lambda n: frameworks[n]["period_end"] or date.min
        )

    fw = frameworks[active_name]
    period_start: date | None = fw["period_start"]
    period_end: date | None = fw["period_end"]

    # Horizon remaining %
    if period_start and period_end and period_end > period_start:
        total_days = (period_end - period_start).days
        remaining_days = max(0, (period_end - today).days)
        inputs.concession_horizon_remaining_pct = round(
            remaining_days / total_days * 100, 2
        )
        years_since = max(0.0, (today - period_start).days / 365.25)
        inputs.years_since_concession_award = round(years_since, 2)

    # Capex completion % from forecast capex (pro-rated for the current year)
    total_capex_allowance: float | None = None
    annual_capex: dict[int, float] = {}
    for r in fw["records"]:
        payload = r.payload or {}
        concept = payload.get("concept")
        raw_val = payload.get("value")
        if raw_val is None:
            continue
        try:
            val = float(raw_val)
        except (TypeError, ValueError):
            continue
        # v1.1 concession concept names (currency-agnostic). Older
        # v1.0 records used …_gbp_million; those have been re-extracted.
        if concept == "capex_allowance_total_million":
            total_capex_allowance = val
            inputs.source_record_ids.append(r.id)
        elif concept == "forecast_capex_million" and r.period_end:
            annual_capex[r.period_end.year] = val
            inputs.source_record_ids.append(r.id)

    if total_capex_allowance and annual_capex:
        cumulative = 0.0
        for year, capex_for_year in sorted(annual_capex.items()):
            if year < today.year:
                cumulative += capex_for_year
            elif year == today.year:
                # Pro-rate by day of year (assume linear deployment within year)
                year_start = date(year, 1, 1)
                fraction = (today - year_start).days / 365
                cumulative += capex_for_year * min(1.0, max(0.0, fraction))
        inputs.capex_programme_completion_pct = round(
            cumulative / total_capex_allowance * 100, 2
        )

    # Methodology notes — be explicit about the assumptions made
    inputs.methodology_notes.append(
        f"regulated airport: '{active_name}' price-control period used as concession proxy"
    )
    if inputs.capex_programme_completion_pct is not None:
        inputs.methodology_notes.append(
            "capex completion derived from forecast capex (not actual deployment) "
            "pro-rated linearly within current year"
        )
    inputs.methodology_notes.append(
        "debt_amortisation_pct and dividend_extraction_pct null — financial "
        "statement data not yet ingested"
    )

    return inputs


# ── Public API ───────────────────────────────────────────────────────────


def compute_for_airport(
    db: Session, airport: Airport, today: date | None = None
) -> ComputedPosition:
    if today is None:
        today = datetime.now(timezone.utc).date()
    inputs = compute_inputs(db, airport, today)
    stage, rationale = classify(inputs)
    return ComputedPosition(
        stage=stage,
        rationale=rationale,
        methodology_version=METHODOLOGY_VERSION_STRING,
        inputs=inputs,
    )


def _get_methodology_version(db: Session) -> MethodologyVersion:
    mv = db.scalar(
        select(MethodologyVersion).where(
            MethodologyVersion.version_string == METHODOLOGY_VERSION_STRING
        )
    )
    if mv is None:
        raise RuntimeError(
            f"Methodology version {METHODOLOGY_VERSION_STRING} not found. "
            "Run `make migrate` to apply migration 003."
        )
    return mv


def persist(db: Session, airport: Airport, position: ComputedPosition) -> None:
    """Write the lifecycle classification onto the airport row."""
    mv = _get_methodology_version(db)
    airport.lifecycle_stage = position.stage
    airport.lifecycle_methodology_version_id = mv.id
    airport.lifecycle_inputs = {
        "rationale": position.rationale,
        **asdict(position.inputs),
    }
    airport.lifecycle_computed_at = datetime.now(timezone.utc)
    db.commit()


def compute_and_persist_all(
    db: Session, iatas: list[str] | None = None, today: date | None = None
) -> dict:
    """Compute lifecycle for the airports listed (default: any with CONCESSION data)."""
    query = select(Airport)
    if iatas:
        query = query.where(Airport.iata_code.in_([i.upper() for i in iatas]))
    else:
        # Default: only airports that have at least one CONCESSION record —
        # for airports with no concession data we'd just emit "indeterminate"
        # everywhere, which adds noise without information.
        query = query.where(
            Airport.id.in_(
                select(DataRecord.airport_id).where(
                    DataRecord.record_type == "CONCESSION",
                    DataRecord.airport_id.is_not(None),
                ).distinct()
            )
        )

    airports = db.scalars(query).all()
    summary: dict[str, Any] = {"computed": 0, "by_stage": {}, "airports": []}

    for airport in airports:
        position = compute_for_airport(db, airport, today)
        persist(db, airport, position)
        summary["computed"] += 1
        summary["by_stage"][position.stage] = summary["by_stage"].get(position.stage, 0) + 1
        summary["airports"].append({
            "iata": airport.iata_code,
            "name": airport.name,
            "stage": position.stage,
            "rationale": position.rationale,
            "horizon_remaining_pct": position.inputs.concession_horizon_remaining_pct,
            "capex_completion_pct": position.inputs.capex_programme_completion_pct,
        })
        logger.info(
            "[%s] lifecycle_stage=%s rationale=%s",
            airport.iata_code or airport.name, position.stage, position.rationale,
        )

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--iata", nargs="*", help="Filter to specific IATA codes")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        summary = compute_and_persist_all(db, iatas=args.iata)
        print(f"\n=== Lifecycle Position v{METHODOLOGY_VERSION_STRING} ===")
        print(f"  computed: {summary['computed']} airports")
        print(f"  by_stage: {summary['by_stage']}")
        print()
        for a in summary["airports"]:
            horizon = f"{a['horizon_remaining_pct']:.1f}%" if a['horizon_remaining_pct'] is not None else "—"
            capex = f"{a['capex_completion_pct']:.1f}%" if a['capex_completion_pct'] is not None else "—"
            print(f"  {a['iata'] or '?':>5} {a['name'][:30]:30s}  stage={a['stage']:13s}  "
                  f"horizon_remaining={horizon:>7s}  capex_completion={capex:>7s}")
            print(f"        rationale: {a['rationale']}")
    finally:
        db.close()
