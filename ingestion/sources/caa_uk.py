"""
CAA UK airport statistics ingestor.

Pulls structured annual traffic data (passengers, ATMs, freight) from the
UK Civil Aviation Authority's annual airport statistics releases. CSV
download per table, free and authoritative — every UK airport reports to
CAA by statute.

Tables ingested (annual):
  - Table 01 — Size of UK Airports → passengers_total
  - Table 05 — Air Transport Movements → air_transport_movements
    (summed across EU / non-EU / domestic columns)
  - Table 13_2 — Freight → cargo_tonnes
    (11-year time series; we emit one record per year per airport)

The annual landing page bundles ~25 CSVs behind opaque /Documents/Download
URLs that change yearly, so we scrape the landing page to discover the
current URLs by link-text match. This means re-running next year requires
no code change — just pass the new year.

Run: uv run python -m ingestion.sources.caa_uk
     uv run python -m ingestion.sources.caa_uk --year 2024
"""

import csv
import io
import logging
import re
from datetime import date, datetime, timezone

import httpx
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport
from ingestion.base import IngestorBase, RawRecord

logger = logging.getLogger(__name__)

SOURCE_ID = "caa_uk"
ANNUAL_PAGE_TEMPLATE = (
    "https://www.caa.co.uk/data-and-analysis/uk-aviation-market/airports/"
    "uk-airport-data/uk-airport-data-{year}/annual-{year}/"
)
CAA_BASE = "https://www.caa.co.uk"
USER_AGENT = "airport-infra-platform alex@endenex.com"

# Link-text fragments → which concept that table feeds. Match is substring
# (case-insensitive) so CAA's small text variations across years don't bite.
TABLE_LINK_PATTERNS = {
    "table 01 size of uk airports": "table_01_passengers",
    "table 05 air transport movements (csv": "table_05_atm",
    "table 13 2 freight": "table_13_freight",
}

# CAA airport names (uppercase as published) → IATA. Covers the top ~30
# commercial UK airports. Anything not in this map lands without airport_id
# (still recorded; just unlinked from the airports table).
CAA_NAME_TO_IATA: dict[str, str] = {
    "HEATHROW": "LHR",
    "GATWICK": "LGW",
    "MANCHESTER": "MAN",
    "STANSTED": "STN",
    "LUTON": "LTN",
    "EDINBURGH": "EDI",
    "BIRMINGHAM": "BHX",
    "BRISTOL": "BRS",
    "GLASGOW": "GLA",
    "BELFAST INTERNATIONAL": "BFS",
    "NEWCASTLE": "NCL",
    "LIVERPOOL (JOHN LENNON)": "LPL",
    "LEEDS BRADFORD": "LBA",
    "EAST MIDLANDS INTERNATIONAL": "EMA",
    "LONDON CITY": "LCY",
    "BELFAST CITY (GEORGE BEST)": "BHD",
    "ABERDEEN": "ABZ",
    "BOURNEMOUTH": "BOH",
    "CARDIFF WALES": "CWL",
    "SOUTHAMPTON": "SOU",
    "INVERNESS": "INV",
    "PRESTWICK": "PIK",
    "EXETER": "EXT",
    "NEWQUAY": "NQY",
    "NORWICH": "NWI",
    "SOUTHEND": "SEN",
    "SUMBURGH": "LSI",
    "DONCASTER SHEFFIELD": "DSA",
    "HUMBERSIDE": "HUY",
    "DURHAM TEES VALLEY": "MME",
    "TEESSIDE INTERNATIONAL AIRPORT": "MME",  # rebranded Durham Tees Valley
    # Smaller regional / Highlands & Islands airports
    "BARRA": "BRR",
    "BENBECULA": "BEB",
    "BIGGIN HILL": "BQH",
    "BLACKPOOL": "BLK",
    "CAMPBELTOWN": "CAL",
    "CITY OF DERRY (EGLINTON)": "LDY",
    "DUNDEE": "DND",
    "FARNBOROUGH": "FAB",
    "ISLAY": "ILY",
    "ISLES OF SCILLY (ST.MARYS)": "ISC",
    "KIRKWALL": "KOI",
    "LANDS END (ST JUST)": "LEQ",
    "LYDD": "LYX",
    "OXFORD (KIDLINGTON)": "OXF",
    "STORNOWAY": "SYY",
    "TIREE": "TRE",
    "WICK JOHN O GROATS": "WIC",
    "ALDERNEY": "ACI",
    "GUERNSEY": "GCI",
    "ISLE OF MAN": "IOM",
    "JERSEY": "JER",
    "COVENTRY": "CVT",
}


def _annual_url(year: int) -> str:
    return ANNUAL_PAGE_TEMPLATE.format(year=year)


def _discover_table_urls(client: httpx.Client, year: int) -> dict[str, str]:
    """
    Scrape the CAA annual landing page for the current year's CSV download
    URLs. Returns {concept_key: absolute_url} for the tables we care about.
    """
    page_url = _annual_url(year)
    resp = client.get(page_url)
    resp.raise_for_status()

    found: dict[str, str] = {}
    # Each download link is <a href="/Documents/Download/...">Table NN ... (CSV document)</a>
    for match in re.finditer(
        r'<a[^>]+href="(/Documents/Download[^"]+)"[^>]*>([^<]+?)</a>',
        resp.text,
    ):
        href, text = match.group(1).strip(), match.group(2).strip().lower()
        for pattern, concept_key in TABLE_LINK_PATTERNS.items():
            if pattern in text and concept_key not in found:
                found[concept_key] = CAA_BASE + href
                break

    missing = set(TABLE_LINK_PATTERNS.values()) - set(found)
    if missing:
        logger.warning("CAA %d: could not discover URLs for %s", year, sorted(missing))
    return found


def _parse_int(s: str) -> int | None:
    """Permissive int parser — strips commas, returns None on failure."""
    if not s or s.strip() in ("..", "-", "n/a", "N/A", ""):
        return None
    try:
        return int(float(s.replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def _parse_float(s: str) -> float | None:
    if not s or s.strip() in ("..", "-", "n/a", "N/A", ""):
        return None
    try:
        return float(s.replace(",", "").strip())
    except (ValueError, TypeError):
        return None


class CaaUkIngestor(IngestorBase):
    source_id = SOURCE_ID

    def __init__(self, year: int) -> None:
        self.year = year
        self._client: httpx.Client | None = None

    def __enter__(self) -> "CaaUkIngestor":
        self._client = httpx.Client(
            timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            )
        return self._client

    # ── fetch ────────────────────────────────────────────────────────────

    def fetch(self) -> dict[str, str]:
        """Returns {concept_key: csv_text} for each discoverable table."""
        urls = _discover_table_urls(self._http(), self.year)
        out: dict[str, str] = {}
        for key, url in urls.items():
            try:
                r = self._http().get(url)
                r.raise_for_status()
                out[key] = r.text
                logger.info("CAA %d %s: %d bytes from %s", self.year, key, len(r.content), url)
            except Exception as exc:
                logger.warning("CAA %d %s: failed to fetch — %s", self.year, key, exc)
        return out

    # ── parse ────────────────────────────────────────────────────────────

    def parse(self, raw: dict[str, str]) -> list[RawRecord]:
        records: list[RawRecord] = []
        retrieved_at = datetime.now(timezone.utc)

        if "table_01_passengers" in raw:
            records.extend(self._parse_table_01(raw["table_01_passengers"], retrieved_at))
        if "table_05_atm" in raw:
            records.extend(self._parse_table_05(raw["table_05_atm"], retrieved_at))
        if "table_13_freight" in raw:
            records.extend(self._parse_table_13(raw["table_13_freight"], retrieved_at))

        logger.info("CAA %d: parsed %d records", self.year, len(records))
        return records

    def _parse_table_01(self, csv_text: str, retrieved_at: datetime) -> list[RawRecord]:
        """Table 01: airport, this_year_pax. One record per airport."""
        rows: list[RawRecord] = []
        reader = csv.DictReader(io.StringIO(csv_text))
        url = _annual_url(self.year)
        for row in reader:
            airport_name = (row.get("airport_name") or "").strip()
            if not airport_name:
                continue
            pax = _parse_int(row.get("this_year_pax", ""))
            if pax is None or pax <= 0:
                continue
            period_end = date(self.year, 12, 31)
            # entity_key encodes the airport identity; the iata is resolved
            # post-commit so it can be remapped without breaking idempotency.
            entity_key = f"{airport_name}:passengers_total:{period_end.isoformat()}"
            rows.append(RawRecord(
                entity_key=entity_key,
                source_url=url,
                source_document_id=f"caa_uk:annual:{self.year}:table_01",
                retrieved_at=retrieved_at,
                record_type="OPERATIONAL",
                period_start=date(self.year, 1, 1).isoformat(),
                period_end=period_end.isoformat(),
                airport_id=None,
                payload={
                    "caa_airport_name": airport_name,
                    "concept": "passengers_total",
                    "value": float(pax),
                    "unit": "passengers",
                    "source_table": "table_01",
                },
            ))
        return rows

    def _parse_table_05(self, csv_text: str, retrieved_at: datetime) -> list[RawRecord]:
        """
        Table 05: ATMs split by route type. We sum Total_EU_ATM +
        total_non_EU_international_atm + total_domestic_atm for the airport
        total. CAA's column names use mixed case — match case-insensitively.
        """
        rows: list[RawRecord] = []
        reader = csv.DictReader(io.StringIO(csv_text))
        # Find the three column names we need, case-insensitively
        if not reader.fieldnames:
            return rows
        cols = {c.lower(): c for c in reader.fieldnames}
        col_eu = cols.get("total_eu_atm")
        col_non_eu = cols.get("total_non_eu_international_atm")
        col_dom = cols.get("total_domestic_atm")
        if not (col_eu and col_non_eu and col_dom):
            logger.warning("Table 05: missing expected ATM columns; got %s", reader.fieldnames)
            return rows

        url = _annual_url(self.year)
        for row in reader:
            airport_name = (row.get("rpt_apt_name") or "").strip()
            if not airport_name:
                continue
            eu = _parse_int(row[col_eu]) or 0
            non_eu = _parse_int(row[col_non_eu]) or 0
            dom = _parse_int(row[col_dom]) or 0
            total_atm = eu + non_eu + dom
            if total_atm <= 0:
                continue
            period_end = date(self.year, 12, 31)
            entity_key = f"{airport_name}:air_transport_movements:{period_end.isoformat()}"
            rows.append(RawRecord(
                entity_key=entity_key,
                source_url=url,
                source_document_id=f"caa_uk:annual:{self.year}:table_05",
                retrieved_at=retrieved_at,
                record_type="OPERATIONAL",
                period_start=date(self.year, 1, 1).isoformat(),
                period_end=period_end.isoformat(),
                airport_id=None,
                payload={
                    "caa_airport_name": airport_name,
                    "concept": "air_transport_movements",
                    "value": float(total_atm),
                    "unit": "movements",
                    "breakdown": {
                        "eu_international": eu,
                        "non_eu_international": non_eu,
                        "domestic": dom,
                    },
                    "source_table": "table_05",
                },
            ))
        return rows

    def _parse_table_13(self, csv_text: str, retrieved_at: datetime) -> list[RawRecord]:
        """
        Table 13_2: freight time series. Columns yr01..yr11 cover the span
        in the `span` column ("2014 - 2024" → yr01=2014, yr11=2024).
        Emit one record per (airport, year) where freight > 0.
        """
        rows: list[RawRecord] = []
        reader = csv.DictReader(io.StringIO(csv_text))
        url = _annual_url(self.year)
        for row in reader:
            airport_name = (row.get("rpt_apt_name") or "").strip()
            if not airport_name:
                continue
            span = row.get("span", "").strip()
            m = re.match(r"(\d{4})\s*-\s*(\d{4})", span)
            if not m:
                continue
            start_year, end_year = int(m.group(1)), int(m.group(2))
            for i in range(1, 12):  # yr01..yr11
                year = start_year + (i - 1)
                if year > end_year:
                    break
                tonnes = _parse_float(row.get(f"yr{i:02d}", ""))
                if tonnes is None or tonnes <= 0:
                    continue
                period_end = date(year, 12, 31)
                entity_key = f"{airport_name}:cargo_tonnes:{period_end.isoformat()}"
                rows.append(RawRecord(
                    entity_key=entity_key,
                    source_url=url,
                    source_document_id=f"caa_uk:annual:{self.year}:table_13:{year}",
                    retrieved_at=retrieved_at,
                    record_type="OPERATIONAL",
                    period_start=date(year, 1, 1).isoformat(),
                    period_end=period_end.isoformat(),
                    airport_id=None,
                    payload={
                        "caa_airport_name": airport_name,
                        "concept": "cargo_tonnes",
                        "value": tonnes,
                        "unit": "tonnes",
                        "source_table": "table_13",
                    },
                ))
        return rows

    # ── airport linkage (post-commit, same pattern as ESMA/CH) ────────────

    def run(self, db: Session):
        result = super().run(db)
        # Always link — the linker is idempotent (only updates airport_id IS NULL
        # rows) and lets a CAA_NAME_TO_IATA edit back-fill existing records on
        # re-run without forcing a re-ingestion.
        self._link_airport_ids(db)
        return result

    def _link_airport_ids(self, db: Session) -> None:
        """
        Resolve caa_airport_name → airports.id for unlinked CAA records.
        Mapping lives in CAA_NAME_TO_IATA (Python-side), which can evolve
        across releases without re-triggering re-ingestion of older records.
        """
        from backend.models import DataRecord
        for caa_name, iata in sorted(CAA_NAME_TO_IATA.items()):
            airport = db.query(Airport).filter_by(iata_code=iata).first()
            if airport is None:
                continue
            db.query(DataRecord).filter(
                DataRecord.source_id == SOURCE_ID,
                DataRecord.payload["caa_airport_name"].astext == caa_name,
                DataRecord.airport_id.is_(None),
            ).update({"airport_id": airport.id}, synchronize_session=False)
        db.commit()


def run_all(db: Session, years: list[int] | None = None) -> dict:
    """Run the ingestor across the supplied years (default: most recent complete year)."""
    if not years:
        # Default to "last calendar year" — CAA publishes annuals a few months
        # after year-end, so this is generally available.
        years = [datetime.now(timezone.utc).year - 1]

    totals: dict = {"created": 0, "skipped": 0, "errors": []}
    for year in years:
        try:
            with CaaUkIngestor(year=year) as ingestor:
                result = ingestor.run(db)
            totals["created"] += result.records_created
            totals["skipped"] += result.records_skipped
            for err in result.errors:
                totals["errors"].append(f"{year}: {err}")
            logger.info("CAA %d done: created=%d skipped=%d",
                        year, result.records_created, result.records_skipped)
        except Exception as exc:
            logger.error("CAA %d failed: %s", year, exc)
            totals["errors"].append(f"{year}: {exc}")
    return totals


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--year", type=int, nargs="*",
        help="Year(s) to ingest (default: last calendar year)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = run_all(db, years=args.year)
        print(f"CAA UK: created={result['created']} skipped={result['skipped']} errors={result['errors']}")
    finally:
        db.close()
