"""
OurAirports reference data ingestor.

Populates the airports master table from the OurAirports global CSV.
85,346 airports total; we filter to commercial airports with scheduled
service (~3,300). All start at tier=5 and get promoted as financial/
operational data arrives from subsequent ingestors.

Run: uv run python -m ingestion.sources.ourairports
"""

import csv
import io
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from backend.db.connection import SessionLocal
from backend.models import Airport, IngestionRun

logger = logging.getLogger(__name__)

SOURCE_ID = "ourairports"
URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

# Only ingest airports where institutional investors might have exposure
COMMERCIAL_TYPES = {"large_airport", "medium_airport", "small_airport"}


def run(db: Session) -> dict:
    ingestion_run = IngestionRun(source_id=SOURCE_ID, status="running")
    db.add(ingestion_run)
    db.flush()

    try:
        logger.info("Fetching OurAirports CSV from %s", URL)
        resp = httpx.get(URL, timeout=120, follow_redirects=True)
        resp.raise_for_status()

        reader = csv.DictReader(io.StringIO(resp.text))
        created = updated = skipped = 0

        for row in reader:
            if row["type"] not in COMMERCIAL_TYPES:
                continue
            if row["scheduled_service"] != "yes":
                continue

            iata = row["iata_code"].strip() or None
            # gps_code is the proper 4-letter ICAO code; ident may be a longer FAA/local code
            icao = row["gps_code"].strip() or None
            ident = row["ident"].strip() or None  # OurAirports primary key, stored separately

            # Skip if we have nothing to link on
            if not iata and not ident:
                skipped += 1
                continue

            # Deduplication: check ident first (most stable), then IATA, then ICAO
            existing = None
            if ident:
                existing = db.query(Airport).filter_by(ourairports_ident=ident).first()
            if not existing and iata:
                existing = db.query(Airport).filter_by(iata_code=iata).first()
            if not existing and icao:
                existing = db.query(Airport).filter_by(icao_code=icao).first()

            fields = {
                "iata_code": iata,
                "icao_code": icao,
                "ourairports_ident": ident,
                "name": row["name"].strip(),
                "country_code": row["iso_country"].strip() or None,
                "city": row["municipality"].strip() or None,
                "latitude": float(row["latitude_deg"]) if row["latitude_deg"].strip() else None,
                "longitude": float(row["longitude_deg"]) if row["longitude_deg"].strip() else None,
                "tier": 5,  # promoted as financial/operational data arrives
            }

            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(Airport(**fields))
                created += 1

        db.flush()
        total = created + updated + skipped
        ingestion_run.status = "completed"
        ingestion_run.completed_at = datetime.now(timezone.utc)
        ingestion_run.records_fetched = total
        ingestion_run.records_created = created
        ingestion_run.records_skipped = skipped
        ingestion_run.metadata_ = {"updated": updated}
        db.commit()

        result = {"created": created, "updated": updated, "skipped": skipped}
        logger.info("OurAirports done: %s", result)
        return result

    except Exception as exc:
        db.rollback()
        ingestion_run.status = "failed"
        ingestion_run.error_message = str(exc)
        ingestion_run.completed_at = datetime.now(timezone.utc)
        db.add(ingestion_run)
        db.commit()
        logger.error("OurAirports failed: %s", exc)
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    db = SessionLocal()
    try:
        result = run(db)
        print(f"airports created={result['created']} updated={result['updated']} skipped={result['skipped']}")
    finally:
        db.close()
