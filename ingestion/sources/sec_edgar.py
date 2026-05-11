"""
SEC EDGAR XBRL Company Facts ingestor.

Fetches structured financial facts for US/ADR-listed airport operators
via the SEC EDGAR Company Facts API. No auth — User-Agent header only.

Known entities (from data/sources/sec_edgar_xbrl.json):
  OMA, GAP, ASUR, CAAP (covers 50+ airports)

Run: uv run python -m ingestion.sources.sec_edgar
"""

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport
from ingestion.base import IngestorBase, RawRecord

logger = logging.getLogger(__name__)

SOURCE_ID = "sec_edgar_xbrl"
BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

HEADERS = {
    "User-Agent": "airport-infra-platform alex@endenex.com",
    "Accept": "application/json",
}

# CIK → (IATA, name)
KNOWN_ENTITIES: dict[str, tuple[str | None, str]] = {
    "0001378239": (None,  "OMA (Central North Airport Group)"),
    "0001347557": (None,  "GAP (Pacific Airport Group)"),
    "0001123452": (None,  "ASUR (Southeast Airport Group)"),
    "0001717393": (None,  "CAAP (Corporación América Airports)"),
}

# GAAP / IFRS concepts to extract
TARGET_CONCEPTS = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "Assets",
    "Liabilities",
    "CashAndCashEquivalentsAtCarryingValue",
    "StockholdersEquity",
}


class SecEdgarIngestor(IngestorBase):
    source_id = SOURCE_ID

    def __init__(self, cik: str, iata: str | None, entity_name: str) -> None:
        self.cik = cik
        self.iata = iata
        self.entity_name = entity_name

    def fetch(self) -> dict:
        url = BASE_URL.format(cik=self.cik)
        resp = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        logger.info("%s: fetched company facts (%d bytes)", self.entity_name, len(resp.content))
        return data

    def parse(self, raw: dict) -> list[RawRecord]:
        records = []
        retrieved_at = datetime.now(timezone.utc)
        source_url = BASE_URL.format(cik=self.cik)

        # Company facts are nested under us-gaap or ifrs-full taxonomy
        facts_container = raw.get("facts", {})
        for taxonomy, concepts in facts_container.items():
            for concept, concept_data in concepts.items():
                if concept not in TARGET_CONCEPTS:
                    continue

                units = concept_data.get("units", {})
                for unit, entries in units.items():
                    for entry in entries:
                        form = entry.get("form", "")
                        # Only annual filings (10-K, 20-F, or equivalent)
                        if not any(f in form for f in ("10-K", "20-F", "40-F")):
                            continue

                        end_date = entry.get("end")
                        if not end_date:
                            continue

                        entity_key = f"{self.cik}:{taxonomy}:{concept}:{end_date}:{entry.get('accn','')}"

                        records.append(RawRecord(
                            entity_key=entity_key,
                            source_url=source_url,
                            source_document_id=entry.get("accn"),
                            retrieved_at=retrieved_at,
                            record_type="FINANCIAL",
                            period_start=entry.get("start"),
                            period_end=end_date,
                            payload={
                                "cik": self.cik,
                                "entity_name": self.entity_name,
                                "taxonomy": taxonomy,
                                "concept": concept,
                                "value": entry.get("val"),
                                "unit": unit,
                                "form": form,
                                "filed": entry.get("filed"),
                                "frame": entry.get("frame"),
                            },
                        ))

        logger.info("%s: parsed %d annual filing facts", self.entity_name, len(records))
        return records


def run_all(db: Session, ciks: list[str] | None = None) -> dict:
    targets = {
        cik: info
        for cik, info in KNOWN_ENTITIES.items()
        if ciks is None or cik in ciks
    }
    totals = {"created": 0, "skipped": 0, "errors": []}
    for cik, (iata, name) in targets.items():
        try:
            ingestor = SecEdgarIngestor(cik=cik, iata=iata, entity_name=name)
            result = ingestor.run(db)
            totals["created"] += result.records_created
            totals["skipped"] += result.records_skipped
            logger.info("%s done: created=%d skipped=%d", name, result.records_created, result.records_skipped)
        except Exception as exc:
            logger.error("%s failed: %s", name, exc)
            totals["errors"].append(f"{name}: {exc}")
    return totals


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    db = SessionLocal()
    try:
        # Default: OMA + CAAP; pass CIKs as args to override
        ciks = sys.argv[1:] or ["0001378239", "0001717393"]
        result = run_all(db, ciks=ciks)
        print(f"SEC EDGAR: created={result['created']} skipped={result['skipped']} errors={result['errors']}")
    finally:
        db.close()
