"""
ESMA XBRL ingestor — filings.xbrl.org JSON:API.

Fetches structured financial facts for EU-listed airport operators.
Approach:
  1. GET /api/filings?filter[entity.identifier]={LEI} → list of filings
  2. For each filing, GET json_url → XBRL-JSON fact bundle (~5-20MB)
  3. Filter to target concepts, parse period and value, write data_records

Known entities (from data/sources/esma_xbrl.json):
  AENA, AdP, Flughafen Wien, Toscana Aeroporti, Bologna, Copenhagen, Malta

Run: uv run python -m ingestion.sources.esma_xbrl
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport
from ingestion.base import IngestorBase, RawRecord

logger = logging.getLogger(__name__)

SOURCE_ID = "esma_xbrl"
FILINGS_BASE = "https://filings.xbrl.org"
FILINGS_URL = f"{FILINGS_BASE}/api/filings"

# LEI → (IATA code, human name)
KNOWN_ENTITIES: dict[str, tuple[str | None, str]] = {
    "959800R7QMXKF0NFMT29": ("MAD", "AENA"),
    "969500PJMBSFHYC37989": ("CDG", "Aéroports de Paris"),
    "549300FQ2ILBH7DJ6I45": ("VIE", "Flughafen Wien"),
    "8156005DBE6CA468DD09": (None,  "Toscana Aeroporti"),
    "8156004CC118B7885065": ("BLQ", "Aeroporto Bologna"),
    "549300Z01GJGM7D3HQ74": ("CPH", "Copenhagen Airports"),
    "2138008EKXNMKZRXCT63": ("MLA", "Malta International Airport"),
}

# XBRL concept names we care about — revenue, profit, assets, liabilities
TARGET_CONCEPTS = {
    "ifrs-full:Revenue",
    "ifrs-full:ProfitLossFromOperatingActivities",
    "ifrs-full:ProfitLoss",
    "ifrs-full:Assets",
    "ifrs-full:Liabilities",
    "ifrs-full:CashAndCashEquivalents",
    "ifrs-full:Equity",
    "ifrs-full:PropertyPlantAndEquipment",
}


def _decrement_if_midnight(iso_dt: str) -> str:
    """
    XBRL/ESEF convention: an instant or duration-end encoded with time 00:00:00
    means "start of that day" — so as a human-friendly "as of" date it
    represents the close of the PREVIOUS day. E.g. PP&E at "2023-01-01T00:00:00"
    means the balance at end of 2022-12-31.
    """
    if "T" not in iso_dt:
        return iso_dt  # already a plain date
    date_part, time_part = iso_dt.split("T", 1)
    # Strip timezone suffix if present (Z, +HH:MM)
    time_only = time_part.split("Z")[0].split("+")[0].split("-")[0]
    if time_only.startswith("00:00:00"):
        try:
            d = datetime.fromisoformat(date_part).date()
            return (d - timedelta(days=1)).isoformat()
        except ValueError:
            return date_part
    return date_part


def _parse_period(period_str: str) -> tuple[str | None, str | None]:
    """
    Parse XBRL period string into (start, end) ISO dates.

    Duration form: "2022-01-01T00:00:00/2023-01-01T00:00:00" → ("2022-01-01", "2022-12-31")
                   (end is exclusive; subtract 1 day for inclusive period_end)
    Instant form:  "2023-01-01T00:00:00" → (None, "2022-12-31")
                   (instant at midnight = balance at close of previous day)
    """
    if not period_str:
        return None, None
    if "/" in period_str:
        start_raw, end_raw = period_str.split("/", 1)
        # Start: take the date as-is (start of day is fine)
        start = start_raw.split("T")[0]
        end = _decrement_if_midnight(end_raw)
        return start, end
    # Instant
    return None, _decrement_if_midnight(period_str)


def _coerce_numeric(value) -> float | None:
    """Convert XBRL value (often a string) to float; return None for non-numeric."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() in {"nil", "n/a", "none"}:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


class EsmaXbrlIngestor(IngestorBase):
    source_id = SOURCE_ID

    def __init__(self, lei: str, iata: str | None, entity_name: str) -> None:
        self.lei = lei
        self.iata = iata
        self.entity_name = entity_name
        self._client: httpx.Client | None = None

    def __enter__(self) -> "EsmaXbrlIngestor":
        self._client = httpx.Client(timeout=60, follow_redirects=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60, follow_redirects=True)
        return self._client

    def _get_airport_id(self, db: Session):
        if not self.iata:
            return None
        a = db.query(Airport).filter_by(iata_code=self.iata).first()
        return a.id if a else None

    def _fetch_filings(self) -> list[dict]:
        resp = self._http().get(
            FILINGS_URL,
            params={"filter[entity.identifier]": self.lei, "page[size]": 50},
        )
        resp.raise_for_status()
        filings = resp.json().get("data", [])
        logger.info("%s: found %d filings", self.entity_name, len(filings))
        return filings

    def fetch(self) -> list[tuple[dict, dict]]:
        """Returns list of (filing_meta, facts_dict) tuples."""
        filings = self._fetch_filings()
        results = []
        for filing in filings:
            attrs = filing["attributes"]
            json_path = attrs.get("json_url", "")
            if not json_path:
                continue
            json_url = f"{FILINGS_BASE}{json_path}"
            try:
                resp = self._http().get(json_url, timeout=120)
                resp.raise_for_status()
                facts_bundle = resp.json()
                results.append((attrs, facts_bundle.get("facts", {})))
                logger.info(
                    "%s: fetched %s (%d facts, %.1fMB)",
                    self.entity_name,
                    attrs.get("period_end"),
                    len(facts_bundle.get("facts", {})),
                    len(resp.content) / 1_000_000,
                )
            except Exception as exc:
                logger.warning("%s: failed to fetch %s — %s", self.entity_name, json_url, exc)
        return results

    def parse(self, raw: list[tuple[dict, dict]]) -> list[RawRecord]:
        records = []
        retrieved_at = datetime.now(timezone.utc)

        for filing_attrs, facts in raw:
            period_end = filing_attrs.get("period_end", "unknown")
            json_path = filing_attrs.get("json_url", "")
            source_url = f"{FILINGS_BASE}{json_path}"

            for fact_id, fact in facts.items():
                dims = fact.get("dimensions", {})
                concept = dims.get("concept", "")
                if concept not in TARGET_CONCEPTS:
                    continue

                raw_value = fact.get("value")
                numeric_value = _coerce_numeric(raw_value)
                if numeric_value is None:
                    continue

                period_str = dims.get("period", "")
                period_start, period_end_parsed = _parse_period(period_str)

                # Include json_path to scope fact_id — fact IDs like f1/f2 reset per filing
                filing_slug = json_path.rstrip("/").split("/")[-1].replace(".json", "")[:32]
                entity_key = f"{self.lei}:{concept}:{period_end_parsed}:{filing_slug}:{fact_id[:16]}"

                records.append(RawRecord(
                    entity_key=entity_key,
                    source_url=source_url,
                    source_document_id=f"lei:{self.lei}:period:{period_end}",
                    retrieved_at=retrieved_at,
                    record_type="FINANCIAL",
                    period_start=period_start,
                    period_end=period_end_parsed,
                    payload={
                        "lei": self.lei,
                        "entity_name": self.entity_name,
                        "concept": concept,
                        "value": numeric_value,
                        "value_raw": raw_value,
                        "decimals": fact.get("decimals"),
                        "unit": dims.get("unit", "").replace("iso4217:", ""),
                        "filing_period_end": period_end,
                        "xbrl_period": period_str,
                    },
                ))

        logger.info("%s: parsed %d target-concept facts across all filings", self.entity_name, len(records))
        return records

    def run(self, db: Session):
        airport_id = self._get_airport_id(db)
        result = super().run(db)
        if airport_id and result.records_created > 0:
            from backend.models import DataRecord
            (
                db.query(DataRecord)
                .filter(
                    DataRecord.source_id == SOURCE_ID,
                    DataRecord.payload["lei"].astext == self.lei,
                    DataRecord.airport_id.is_(None),
                )
                .update({"airport_id": airport_id}, synchronize_session=False)
            )
            db.commit()
        return result


def run_all(db: Session, leis: list[str] | None = None) -> dict:
    targets = {
        lei: info
        for lei, info in KNOWN_ENTITIES.items()
        if leis is None or lei in leis
    }
    totals: dict = {"created": 0, "skipped": 0, "errors": []}
    for lei, (iata, name) in targets.items():
        try:
            with EsmaXbrlIngestor(lei=lei, iata=iata, entity_name=name) as ingestor:
                result = ingestor.run(db)
            totals["created"] += result.records_created
            totals["skipped"] += result.records_skipped
            for err in result.errors:
                totals["errors"].append(f"{name}: {err}")
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
        leis = sys.argv[1:] or ["959800R7QMXKF0NFMT29"]
        result = run_all(db, leis=leis)
        print(f"ESMA XBRL: created={result['created']} skipped={result['skipped']} errors={result['errors']}")
    finally:
        db.close()
