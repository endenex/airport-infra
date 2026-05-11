"""
Generic disclosure-document → LLM-extraction runner.

Iterates over a registry of airport disclosure PDFs, fetches each (with
content-hash R2 storage), invokes an `LLMPipelineBase` to extract typed
records, and persists with confidence routing.

The cache check is scoped by `(content_hash, pipeline.record_type)` so the
same PDF can feed multiple pipelines without their caches interfering.

Inter-call throttling keeps batches under Anthropic's per-minute token
budget. Cache hits skip the throttle since they don't burn tokens.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import Airport, DataRecord, IngestionRun
from ingestion.documents import extract_pdf_text, fetch_and_store
from llm_pipelines.base import ExtractionResult, LLMPipelineBase

logger = logging.getLogger(__name__)


@dataclass
class Disclosure:
    """One airport disclosure document and how to attribute its extractions."""

    iata: str  # for airport_id lookup
    entity_name: str
    key: str  # stable doc identifier, used in entity_key_prefix
    url: str
    reporting_period_end: str  # YYYY-MM-DD
    kind: str  # "sustainability" | "annual_report" | "monitoring" | "regulatory"
    source_id: str  # data_records.source_id namespace (e.g. "heathrow_direct")
    # Optional regulator metadata — set for kind="regulatory" disclosures.
    # These travel through context so the pipeline can use them in the prompt
    # and stamp them onto extracted records without re-asking the LLM.
    regulator_name: str | None = None
    regulatory_framework_name: str | None = None
    regulatory_period_start: str | None = None  # YYYY-MM-DD
    regulatory_period_end: str | None = None    # YYYY-MM-DD


# Single authoritative registry of UK airport disclosure documents.
# Manchester Airports Group runs MAN/EMA/STN under one disclosure — we
# attribute MAG-level emissions to MAN (the largest) and carry the "(MAG)"
# qualifier in entity_name so it's explicit in queries.
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


# Regulatory price-control decisions. These are PDF-only by definition (no
# regulator publishes a structured RAB/WACC API), so this is the appropriate
# place for LLM extraction per the source-precedence rule.
#
# Network operators (AENA, ADP) regulate at the portfolio level — DORA II
# governs all ~50 AENA airports collectively, CRE governs CDG + ORY + LBG
# together. We attribute the regulatory record to the operator's hub airport
# (MAD for AENA, CDG for ADP) and document the choice; future work should
# add a proper portfolio-to-airport mapping so the same decision shows up
# on every airport in the network.
REGULATORY_DISCLOSURES: list[Disclosure] = [
    Disclosure(
        iata="LHR",
        entity_name="Heathrow Airport Limited",
        key="caa_h7_final_decision_summary",
        url="https://www.caa.co.uk/publication/download/20187",  # CAP2524A summary
        reporting_period_end="2023-03-08",  # publication date as the "report period" anchor
        kind="regulatory",
        source_id="caa_h7",
        regulator_name="UK Civil Aviation Authority",
        regulatory_framework_name="H7",
        regulatory_period_start="2022-01-01",
        regulatory_period_end="2026-12-31",
    ),
    Disclosure(
        iata="MAD",
        entity_name="AENA (DORA II — Spain airport network regulation)",
        key="aena_dora_ii_2022_2026",
        url="https://www.transportes.gob.es/recursos_mfom/dora_2022-2026.pdf",
        reporting_period_end="2021-09-28",  # Council of Ministers approval date
        kind="regulatory",
        source_id="aena_dora",
        regulator_name="Ministerio de Transportes y Movilidad Sostenible (Spain)",
        regulatory_framework_name="DORA II",
        regulatory_period_start="2022-01-01",
        regulatory_period_end="2026-12-31",
    ),
    # ADP CRE 4 (2027-2034) is in proposal phase and no clean PDF URL is
    # publicly disseminated yet. Re-add this entry when the ART/État sign
    # the final document. The previous CRE 3 (2016-2020) is concluded and
    # historical; not useful for current-period lifecycle calculations.
]

# Anthropic Haiku 4.5 free-tier limit is 50K input tokens/min. At ~4 chars
# per token, 150K chars ≈ 37K tokens — leaves headroom for the prompt
# (~5K tokens) so a single doc fits inside one rate-limit window.
MAX_PDF_CHARS = 150_000
INTER_CALL_SLEEP_SECONDS = 65


def _get_airport_id(db: Session, iata: str) -> uuid.UUID | None:
    airport = db.query(Airport).filter_by(iata_code=iata).first()
    return airport.id if airport else None


def _run_one(
    db: Session,
    disclosure: Disclosure,
    airport_id: uuid.UUID | None,
    ingestion_run_id: uuid.UUID,
    pipeline: LLMPipelineBase,
    force: bool = False,
) -> tuple[dict, bool]:
    """
    Fetch one document, extract typed facts, persist.
    Returns (counts, llm_called) — llm_called is False when the cache hit.
    """
    fetched = fetch_and_store(disclosure.url, source_id=disclosure.source_id)
    logger.info(
        "[%s/%s] Fetched %s: %.1fMB, hash=%s",
        disclosure.iata, pipeline.record_type, disclosure.key,
        fetched.size_bytes / 1_000_000, fetched.content_hash[:12],
    )

    if not force:
        existing = (
            db.query(DataRecord)
            .filter(
                DataRecord.source_document_id == fetched.content_hash,
                DataRecord.record_type == pipeline.record_type,
            )
            .count()
        )
        if existing > 0:
            logger.info(
                "[%s/%s] Skipping LLM — %d records exist for hash %s",
                disclosure.iata, pipeline.record_type, existing, fetched.content_hash[:12],
            )
            return ({"created": 0, "skipped": existing, "auto_approved": 0,
                     "pending_review": 0, "fetched": 0, "errors": 0}, False)

    text = extract_pdf_text(fetched.content_bytes, max_chars=MAX_PDF_CHARS)
    logger.info(
        "[%s/%s] Extracted %d chars (capped at %d)",
        disclosure.iata, pipeline.record_type, len(text), MAX_PDF_CHARS,
    )

    context = {
        "entity_name": disclosure.entity_name,
        "entity_key_prefix": disclosure.key,
        "source_url": disclosure.url,
        "source_document_id": fetched.content_hash,
        "reporting_period_end": disclosure.reporting_period_end,
        "airport_id": airport_id,
    }
    # Carry through optional regulator metadata when present — concession
    # pipeline uses these to stamp records and to ground the LLM prompt.
    for attr in ("regulator_name", "regulatory_framework_name",
                 "regulatory_period_start", "regulatory_period_end"):
        v = getattr(disclosure, attr, None)
        if v is not None:
            context[attr] = v

    result: ExtractionResult = pipeline.extract(text, context)
    if result.errors:
        logger.error(
            "[%s/%s] Extraction errors: %s",
            disclosure.iata, pipeline.record_type, result.errors,
        )

    counts = pipeline.persist(result, db, ingestion_run_id=ingestion_run_id)
    counts["fetched"] = len(result.records)
    counts["errors"] = len(result.errors)
    return counts, True


def run_disclosures(
    db: Session,
    pipeline: LLMPipelineBase,
    *,
    disclosures: list[Disclosure] | None = None,
    iatas: list[str] | None = None,
    force: bool = False,
    inter_call_sleep_seconds: int = INTER_CALL_SLEEP_SECONDS,
) -> dict:
    """
    Run a pipeline across a list of disclosures.

    disclosures defaults to UK_DISCLOSURES. iatas, if given, filters.
    inter_call_sleep_seconds=0 disables throttling (use with care).
    """
    targets = list(disclosures if disclosures is not None else UK_DISCLOSURES)
    if iatas:
        targets = [d for d in targets if d.iata in iatas]

    ingestion_run = IngestionRun(
        source_id=f"llm:{pipeline.record_type.lower()}",
        status="running",
    )
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
                logger.warning(
                    "[%s/%s] no airport row — records will lack airport_id",
                    disclosure.iata, pipeline.record_type,
                )

            # Throttle if we made an LLM call last iteration. Cache hits don't
            # burn tokens, so they don't trigger the sleep.
            if last_llm_call is not None and i > 0 and inter_call_sleep_seconds > 0:
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
            logger.info("[%s/%s] done: %s", disclosure.iata, pipeline.record_type, counts)
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
