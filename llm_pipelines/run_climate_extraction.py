"""
CLIMATE extraction runner.

Iterates over a registry of airport disclosure documents (sustainability
reports, annual reports, monitoring reports), fetches each, extracts
climate KPIs via Claude, and persists with confidence routing.

Idempotent: re-runs short-circuit before the LLM call when CLIMATE records
already exist for the document's content hash.

Run: uv run python -m llm_pipelines.run_climate_extraction
     uv run python -m llm_pipelines.run_climate_extraction --iata LHR LGW
     uv run python -m llm_pipelines.run_climate_extraction --force
"""

import argparse
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport, DataRecord, IngestionRun
from ingestion.documents import extract_pdf_text, fetch_and_store
from llm_pipelines.base import ExtractionResult
from llm_pipelines.climate_extraction import ClimateExtractionPipeline

logger = logging.getLogger(__name__)


@dataclass
class Disclosure:
    """One airport disclosure document and how to attribute its extractions."""

    iata: str  # for airport_id lookup
    entity_name: str
    key: str  # stable doc identifier, used in entity_key_prefix
    url: str
    reporting_period_end: str  # YYYY-MM-DD
    kind: str  # "sustainability" | "annual_report" | "monitoring"
    source_id: str  # data_records.source_id namespace (e.g. "heathrow_direct")


# Manchester Airports Group runs MAN, EMA and STN under one corporate
# disclosure. We attribute MAG-level emissions to MAN (the largest of the
# three) for now; the entity_name carries the "MAG" qualifier so it's
# explicit in queries.
UK_DISCLOSURES: list[Disclosure] = [
    Disclosure(
        iata="LHR",
        entity_name="Heathrow Airport Holdings",
        key="heathrow_sustainability_2025",
        url="https://www.heathrow.com/content/dam/heathrow/web/common/documents/company/heathrow-2-0-sustainability/reports/2025/2025_Sustainability_Report.pdf",
        reporting_period_end="2025-12-31",
        kind="sustainability",
        source_id="heathrow_direct",
    ),
    Disclosure(
        iata="LGW",
        entity_name="Gatwick Airport Limited",
        key="gatwick_decade_of_change_2024",
        url="https://www.gatwickairport.com/on/demandware.static/-/Sites-Gatwick-Library/default/dw1dc88e69/images/Corporate-PDFs/Sustainability/Decade%20of%20Change%20reports/DoC%20report%202024%20final.pdf",
        reporting_period_end="2024-12-31",
        kind="sustainability",
        source_id="gatwick_direct",
    ),
    Disclosure(
        iata="MAN",
        entity_name="Manchester Airports Group (MAG)",
        key="mag_net_zero_roadmap_2024",
        url="https://assets.live.dxp.maginfrastructure.com/f/73114/x/eb4273800d/mag-net-zero-carbon-roadmap-june-2024.pdf",
        reporting_period_end="2024-03-31",
        kind="sustainability",
        source_id="mag_direct",
    ),
    Disclosure(
        iata="EDI",
        entity_name="Edinburgh Airport Limited",
        key="edinburgh_greater_good_2024",
        url="https://assets.ctfassets.net/2hwzhse7szu0/5dlOKQTZi7BWOrnxzxKlFb/20a84bc6074b6720078e7f3c9054a955/EDI_Greater_Good_Sustainability_Report_2024__A4__v1_AW.pdf",
        reporting_period_end="2024-12-31",
        kind="sustainability",
        source_id="edinburgh_direct",
    ),
    Disclosure(
        iata="BRS",
        entity_name="Bristol Airport Limited",
        key="bristol_annual_monitoring_2024",
        url="https://www.bristolairport.co.uk/media/as2j1amw/brs-annual-monitoring-report-2024v2-web-version.pdf",
        reporting_period_end="2024-12-31",
        kind="monitoring",
        source_id="bristol_direct",
    ),
    Disclosure(
        iata="BHX",
        entity_name="Birmingham Airport Limited",
        key="birmingham_sustainability_update_2024",
        url="https://assets.ctfassets.net/qacv5m4pr8sy/63Pn6NgsGuQuEEGeZeXCBc/c155224214e077128eb29c0806da8283/Sustainability_Update_2023-2024_FINAL_-_for_web.pdf",
        reporting_period_end="2024-12-31",
        kind="sustainability",
        source_id="birmingham_direct",
    ),
]

# Anthropic Haiku 4.5 free-tier limit is 50K input tokens/min. At ~4 chars
# per token, 150K chars ≈ 37K tokens — leaves headroom for the prompt
# (~5K tokens) so a single doc fits inside one rate-limit window.
MAX_PDF_CHARS = 150_000

# After an LLM call, wait this long before the next one so a multi-doc
# batch stays under the per-minute token budget. Skip the sleep when the
# cache short-circuits (no LLM call was made).
INTER_CALL_SLEEP_SECONDS = 65


def _get_airport_id(db: Session, iata: str) -> uuid.UUID | None:
    airport = db.query(Airport).filter_by(iata_code=iata).first()
    return airport.id if airport else None


def _run_one(
    db: Session,
    disclosure: Disclosure,
    airport_id: uuid.UUID | None,
    ingestion_run_id: uuid.UUID,
    pipeline: ClimateExtractionPipeline,
    force: bool = False,
) -> tuple[dict, bool]:
    """
    Fetch one document, extract climate facts, persist.
    Returns (counts, llm_called) — llm_called is False when the cache hit.
    """
    fetched = fetch_and_store(disclosure.url, source_id=disclosure.source_id)
    logger.info(
        "[%s] Fetched %s: %.1fMB, hash=%s",
        disclosure.iata, disclosure.key, fetched.size_bytes / 1_000_000, fetched.content_hash[:12],
    )

    if not force:
        existing = (
            db.query(DataRecord)
            .filter(
                DataRecord.source_document_id == fetched.content_hash,
                DataRecord.record_type == "CLIMATE",
            )
            .count()
        )
        if existing > 0:
            logger.info(
                "[%s] Skipping LLM — %d climate records exist for hash %s",
                disclosure.iata, existing, fetched.content_hash[:12],
            )
            return ({"created": 0, "skipped": existing, "auto_approved": 0,
                     "pending_review": 0, "fetched": 0, "errors": 0}, False)

    text = extract_pdf_text(fetched.content_bytes, max_chars=MAX_PDF_CHARS)
    logger.info("[%s] Extracted %d chars (capped at %d)", disclosure.iata, len(text), MAX_PDF_CHARS)

    context = {
        "entity_name": disclosure.entity_name,
        "entity_key_prefix": disclosure.key,
        "source_url": disclosure.url,
        "source_document_id": fetched.content_hash,
        "reporting_period_end": disclosure.reporting_period_end,
        "airport_id": airport_id,
    }

    result: ExtractionResult = pipeline.extract(text, context)
    if result.errors:
        logger.error("[%s] Extraction errors: %s", disclosure.iata, result.errors)

    counts = pipeline.persist(result, db, ingestion_run_id=ingestion_run_id)
    counts["fetched"] = len(result.records)
    counts["errors"] = len(result.errors)
    return counts, True


def run(
    db: Session,
    iatas: list[str] | None = None,
    force: bool = False,
    inter_call_sleep_seconds: int = INTER_CALL_SLEEP_SECONDS,
) -> dict:
    """
    Run climate extraction across disclosures.
    iatas=None → all of UK_DISCLOSURES. Otherwise filter by IATA code.
    """
    pipeline = ClimateExtractionPipeline()
    targets = [d for d in UK_DISCLOSURES if iatas is None or d.iata in iatas]

    ingestion_run = IngestionRun(source_id="llm:climate", status="running")
    db.add(ingestion_run)
    db.flush()

    totals: dict[str, int] = {"created": 0, "skipped": 0, "auto_approved": 0,
                              "pending_review": 0, "fetched": 0, "errors": 0}
    failures: list[str] = []
    last_llm_call: float | None = None

    for i, disclosure in enumerate(targets):
        try:
            airport_id = _get_airport_id(db, disclosure.iata)
            if airport_id is None:
                logger.warning("[%s] no airport row — records will lack airport_id", disclosure.iata)

            # Throttle if we're about to make a real LLM call and the previous
            # iteration also made one. Cache-hits don't burn tokens, so they
            # don't trigger the sleep.
            if last_llm_call is not None and i > 0:
                elapsed = time.time() - last_llm_call
                if elapsed < inter_call_sleep_seconds:
                    sleep_for = inter_call_sleep_seconds - elapsed
                    logger.info("Throttling %.0fs to respect rate limit", sleep_for)
                    time.sleep(sleep_for)

            counts, llm_called = _run_one(
                db, disclosure, airport_id, ingestion_run.id, pipeline, force=force
            )
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
            if llm_called:
                last_llm_call = time.time()
            logger.info("[%s] done: %s", disclosure.iata, counts)
        except Exception as exc:
            msg = f"{disclosure.iata}/{disclosure.key}: {type(exc).__name__}: {exc}"
            logger.error(msg)
            failures.append(msg)

    ingestion_run.status = "completed" if not failures else "failed"
    ingestion_run.completed_at = datetime.now(timezone.utc)
    ingestion_run.records_fetched = totals["fetched"]
    ingestion_run.records_created = totals["created"]
    ingestion_run.records_skipped = totals["skipped"]
    if failures:
        ingestion_run.error_message = "; ".join(failures)
    db.commit()

    out: dict = dict(totals)
    out["failures"] = failures
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--iata", nargs="*", help="Filter to specific IATA codes (default: all)")
    parser.add_argument("--force", action="store_true",
                        help="Skip the content-hash cache and re-call the LLM")
    parser.add_argument("--no-throttle", action="store_true",
                        help="Disable inter-call rate-limit sleep (use sparingly)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = run(
            db,
            iatas=args.iata,
            force=args.force,
            inter_call_sleep_seconds=0 if args.no_throttle else INTER_CALL_SLEEP_SECONDS,
        )
        print(
            f"Climate extraction: "
            f"created={result['created']} skipped={result['skipped']} "
            f"auto_approved={result['auto_approved']} pending_review={result['pending_review']} "
            f"errors={result['errors']} failures={result['failures']}"
        )
    finally:
        db.close()
