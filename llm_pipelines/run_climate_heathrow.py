"""
End-to-end CLIMATE extraction for Heathrow.

Fetches Heathrow's Sustainability Report and Annual Report, stores them in
R2, extracts text, calls Claude for structured climate data, routes by
confidence, writes DataRecord + LLMExtraction rows.

Run: uv run python -m llm_pipelines.run_climate_heathrow
     uv run python -m llm_pipelines.run_climate_heathrow --sustainability-only
"""

import argparse
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport, DataRecord, IngestionRun
from ingestion.documents import extract_pdf_text, fetch_and_store
from llm_pipelines.base import ExtractionResult
from llm_pipelines.climate_extraction import ClimateExtractionPipeline

logger = logging.getLogger(__name__)

# Discovered from heathrow.com/company/investor-centre — keep the list
# explicit so we know exactly what we ingested and when. The Sustainability
# Report is the richer climate disclosure source; the ARA carries the
# audited financials but typically also a climate summary.
HEATHROW_DOCUMENTS = [
    {
        "key": "sustainability_2025",
        "url": "https://www.heathrow.com/content/dam/heathrow/web/common/documents/company/heathrow-2-0-sustainability/reports/2025/2025_Sustainability_Report.pdf",
        "reporting_period_end": "2025-12-31",
        "kind": "sustainability",
    },
    {
        "key": "annual_report_2025",
        "url": "https://www.heathrow.com/content/dam/heathrow/web/common/documents/company/investor/reports-and-presentations/annual-accounts/sp/2025_Heathrow_SP_ARA_Signed.pdf",
        "reporting_period_end": "2025-12-31",
        "kind": "annual_report",
    },
]

SOURCE_ID = "heathrow_direct"
LHR_IATA = "LHR"

# Haiku 4.5 context is ~200K tokens; ~4 chars/token gives us a generous
# headroom but Heathrow's sustainability reports are typically 100-200 pages.
# Cap at ~400K chars (~100K tokens) to stay well under the limit and keep
# costs predictable.
MAX_PDF_CHARS = 400_000


def _get_airport_id(db: Session) -> uuid.UUID | None:
    airport = db.query(Airport).filter_by(iata_code=LHR_IATA).first()
    return airport.id if airport else None


def _run_one(
    db: Session,
    doc_spec: dict,
    airport_id: uuid.UUID | None,
    ingestion_run_id: uuid.UUID,
    pipeline: ClimateExtractionPipeline,
    force: bool = False,
) -> dict:
    """Fetch one document, extract climate facts, persist. Returns counts."""
    fetched = fetch_and_store(doc_spec["url"], source_id=SOURCE_ID)
    logger.info(
        "Fetched %s: %.1fMB, hash=%s, r2_key=%s",
        doc_spec["key"],
        fetched.size_bytes / 1_000_000,
        fetched.content_hash[:12],
        fetched.r2_key,
    )

    # Extraction cache: if we already have records for this content_hash via
    # the climate pipeline, skip the LLM call. The deterministic ID handles
    # idempotency at the record level, but skipping the API call saves tokens
    # and avoids rate limits on re-runs.
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
                "Skipping LLM call for %s — %d climate records already exist for content_hash %s",
                doc_spec["key"], existing, fetched.content_hash[:12],
            )
            return {"created": 0, "skipped": existing, "auto_approved": 0,
                    "pending_review": 0, "fetched": 0, "errors": 0}

    text = extract_pdf_text(fetched.content_bytes, max_chars=MAX_PDF_CHARS)
    logger.info("Extracted %d chars of text from %s", len(text), doc_spec["key"])

    context = {
        "entity_name": "Heathrow Airport Holdings",
        "entity_key_prefix": f"heathrow:{doc_spec['key']}",
        "source_url": doc_spec["url"],
        "source_document_id": fetched.content_hash,
        "reporting_period_end": doc_spec["reporting_period_end"],
        "airport_id": airport_id,
    }

    result: ExtractionResult = pipeline.extract(text, context)
    if result.errors:
        logger.error("Extraction errors for %s: %s", doc_spec["key"], result.errors)

    counts = pipeline.persist(result, db, ingestion_run_id=ingestion_run_id)
    counts["fetched"] = len(result.records)
    counts["errors"] = len(result.errors)
    return counts


def run(db: Session, only_kind: str | None = None, force: bool = False) -> dict:
    pipeline = ClimateExtractionPipeline()
    airport_id = _get_airport_id(db)
    if airport_id is None:
        logger.warning("No airport row for IATA=%s — records will lack airport_id", LHR_IATA)

    # One IngestionRun covers all docs in this batch — easy to roll up later.
    ingestion_run = IngestionRun(source_id=f"llm:climate:{SOURCE_ID}", status="running")
    db.add(ingestion_run)
    db.flush()

    totals: dict[str, int] = {"created": 0, "skipped": 0, "auto_approved": 0,
                              "pending_review": 0, "fetched": 0, "errors": 0}
    failures: list[str] = []

    for doc in HEATHROW_DOCUMENTS:
        if only_kind and doc["kind"] != only_kind:
            continue
        try:
            counts = _run_one(db, doc, airport_id, ingestion_run.id, pipeline, force=force)
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
            logger.info("Doc %s done: %s", doc["key"], counts)
        except Exception as exc:
            msg = f"{doc['key']}: {type(exc).__name__}: {exc}"
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
    parser.add_argument("--sustainability-only", action="store_true")
    parser.add_argument("--annual-report-only", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Skip the content-hash cache check and re-call the LLM")
    args = parser.parse_args()

    only_kind = None
    if args.sustainability_only:
        only_kind = "sustainability"
    elif args.annual_report_only:
        only_kind = "annual_report"

    db = SessionLocal()
    try:
        result = run(db, only_kind=only_kind, force=args.force)
        print(
            f"Climate extraction (Heathrow): "
            f"created={result['created']} skipped={result['skipped']} "
            f"auto_approved={result['auto_approved']} pending_review={result['pending_review']} "
            f"errors={result['errors']} failures={result['failures']}"
        )
    finally:
        db.close()
