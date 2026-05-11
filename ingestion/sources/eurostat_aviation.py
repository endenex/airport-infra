"""
Eurostat aviation statistics ingestor (avia_paoa).

Pulls annual passenger totals by airport from Eurostat's free JSON-stat
REST API. Covers ~870 airports across EU + EFTA + Western Balkans + EU
candidate countries. UK airports are listed but report null post-Brexit
(2020+) — CAA covers UK; Eurostat covers everywhere else.

This gives us authoritative operational data for the ESMA-listed
operators (AENA's MAD/BCN/PMI/etc., ADP's CDG/ORY, Wien LOWW, Toscana
FLR/PSA, Bologna BLQ, Copenhagen EKCH, Malta LMML) plus another ~860
European airports as a side-effect.

Run: uv run python -m ingestion.sources.eurostat_aviation
     uv run python -m ingestion.sources.eurostat_aviation --years 2023 2024
"""

import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport
from ingestion.base import IngestorBase, RawRecord

logger = logging.getLogger(__name__)

SOURCE_ID = "eurostat_aviation"
DATASET = "avia_paoa"
API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
USER_AGENT = "airport-infra-platform alex@endenex.com"

# Canonical filter for "total annual passengers carried" — the closest
# Eurostat equivalent to CAA's headline pax figure. We hold these constant
# so cross-source comparisons stay apples-to-apples.
DEFAULT_FILTERS = {
    "freq": "A",          # Annual
    "unit": "PAS",        # Passenger count
    "tra_meas": "PAS_CRD",  # Passengers carried (departures + arrivals, both legs)
    "schedule": "TOT",    # All schedules
    "tra_cov": "TOTAL",   # All route coverage
}


def _split_eurostat_airport_code(code: str) -> tuple[str | None, str | None]:
    """
    Eurostat encodes airports as '{country}_{ICAO}' e.g. 'FR_LFPG'.
    Returns (country, icao) or (None, None) if unparsable.
    """
    if not code or "_" not in code:
        return None, None
    country, icao = code.split("_", 1)
    return country, icao


class EurostatAviationIngestor(IngestorBase):
    source_id = SOURCE_ID

    def __init__(self, year: int) -> None:
        self.year = year
        self._client: httpx.Client | None = None

    def __enter__(self) -> "EurostatAviationIngestor":
        self._client = httpx.Client(
            timeout=90, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=90, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            )
        return self._client

    def fetch(self) -> dict:
        url = f"{API_BASE}/{DATASET}"
        params = {**DEFAULT_FILTERS, "lang": "EN", "format": "JSON", "time": str(self.year)}
        resp = self._http().get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        n_airports = len(data["dimension"]["rep_airp"]["category"]["index"])
        n_values = len(data.get("value", {}))
        logger.info("Eurostat %s %d: %d airports, %d values, %d bytes",
                    DATASET, self.year, n_airports, n_values, len(resp.content))
        return data

    def parse(self, raw: dict) -> list[RawRecord]:
        # JSON-stat 2.0 layout:
        #   dimension.rep_airp.category.index  : {code → flat_index}
        #   dimension.rep_airp.category.label  : {code → human-readable label}
        #   value                              : {flat_index_str → numeric_value}
        # Because all the other dimensions are fixed to single values, the
        # flat index collapses directly to rep_airp's index.
        records: list[RawRecord] = []
        retrieved_at = datetime.now(timezone.utc)
        period_end = date(self.year, 12, 31)
        period_start = date(self.year, 1, 1)
        # The Eurostat page URL is stable per dataset; the underlying data we
        # actually pulled lives at the dissemination API endpoint.
        source_url = (
            f"https://ec.europa.eu/eurostat/databrowser/view/{DATASET}/default/table"
        )

        rep_airp = raw["dimension"]["rep_airp"]["category"]
        indices = rep_airp["index"]
        labels = rep_airp["label"]
        values = raw.get("value", {})

        for eurostat_code, flat_idx in indices.items():
            val = values.get(str(flat_idx))
            if val is None or val <= 0:
                continue
            country, icao = _split_eurostat_airport_code(eurostat_code)
            if icao is None:
                continue

            entity_key = f"{eurostat_code}:passengers_total:{period_end.isoformat()}"
            records.append(RawRecord(
                entity_key=entity_key,
                source_url=source_url,
                source_document_id=f"{DATASET}:{self.year}",
                retrieved_at=retrieved_at,
                record_type="OPERATIONAL",
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
                airport_id=None,  # linked post-commit via ICAO match
                payload={
                    "eurostat_code": eurostat_code,
                    "icao": icao,
                    "country": country,
                    "airport_label": labels.get(eurostat_code),
                    "concept": "passengers_total",
                    "value": float(val),
                    "unit": "passengers",
                    "dataset": DATASET,
                    "filters": DEFAULT_FILTERS,
                },
            ))

        logger.info("Eurostat %d: parsed %d airport-records", self.year, len(records))
        return records

    def run(self, db: Session):
        result = super().run(db)
        # Always run linkage — idempotent (only touches airport_id IS NULL rows)
        self._link_airport_ids(db)
        return result

    def _link_airport_ids(self, db: Session) -> None:
        """
        Resolve payload.icao → airports.id for unlinked records. The ICAO
        is already in payload (and stable across runs), so this is a simple
        JOIN-style update.
        """
        from sqlalchemy import update

        from backend.models import DataRecord
        # Pull all distinct icao codes that have unlinked rows in this source
        unlinked_icaos = {
            row[0] for row in db.query(DataRecord.payload["icao"].astext)
            .filter(
                DataRecord.source_id == SOURCE_ID,
                DataRecord.airport_id.is_(None),
            )
            .distinct()
            .all()
            if row[0]
        }
        if not unlinked_icaos:
            return

        # One query to load the airport ids we care about
        airport_rows = (
            db.query(Airport.id, Airport.icao_code)
            .filter(Airport.icao_code.in_(unlinked_icaos))
            .all()
        )
        for airport_id, icao in airport_rows:
            db.execute(
                update(DataRecord)
                .where(
                    DataRecord.source_id == SOURCE_ID,
                    DataRecord.payload["icao"].astext == icao,
                    DataRecord.airport_id.is_(None),
                )
                .values(airport_id=airport_id)
            )
        db.commit()


def run_all(db: Session, years: list[int] | None = None) -> dict:
    """Default: ingest the last 6 calendar years (covers pre-Covid → latest)."""
    if not years:
        current_year = datetime.now(timezone.utc).year
        years = list(range(current_year - 6, current_year))  # exclusive of current

    totals: dict = {"created": 0, "skipped": 0, "errors": []}
    for year in years:
        try:
            with EurostatAviationIngestor(year=year) as ingestor:
                result = ingestor.run(db)
            totals["created"] += result.records_created
            totals["skipped"] += result.records_skipped
            for err in result.errors:
                totals["errors"].append(f"{year}: {err}")
            logger.info("Eurostat %d done: created=%d skipped=%d",
                        year, result.records_created, result.records_skipped)
        except Exception as exc:
            logger.error("Eurostat %d failed: %s", year, exc)
            totals["errors"].append(f"{year}: {exc}")
    return totals


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs="*",
                        help="Years to ingest (default: last 6 calendar years)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = run_all(db, years=args.years)
        print(f"Eurostat: created={result['created']} skipped={result['skipped']} "
              f"errors={result['errors']}")
    finally:
        db.close()
