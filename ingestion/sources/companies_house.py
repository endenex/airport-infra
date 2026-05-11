"""
Companies House UK ingestor.

Fetches UK company profile and PSC (persons with significant control)
data for airport entities. Writes OWNERSHIP data_records.

Run: uv run python -m ingestion.sources.companies_house
"""

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.connection import SessionLocal
from backend.models import Airport
from ingestion.base import IngestorBase, RawRecord

logger = logging.getLogger(__name__)

SOURCE_ID = "companies_house"
API_BASE = "https://api.company-information.service.gov.uk"

# Company number → (IATA, name)
KNOWN_ENTITIES: dict[str, tuple[str | None, str]] = {
    "01991017": ("LHR", "Heathrow Airport Limited"),
    "05757208": ("LHR", "Heathrow Airport Holdings Limited"),
    "01991018": ("LGW", "Gatwick Airport Limited"),
    "03846135": ("LGW", "Gatwick Funding Limited"),
    "08353309": ("MAN", "Manchester Airports Holdings Limited"),
    "SC096623": ("EDI", "Edinburgh Airport Limited"),
    "02041223": ("BRS", "Bristol Airport Limited"),
    "01773052": ("BHX", "Birmingham Airport Holdings Limited"),
}


class CompaniesHouseIngestor(IngestorBase):
    source_id = SOURCE_ID

    def __init__(self, company_number: str, iata: str | None, entity_name: str) -> None:
        self.company_number = company_number
        self.iata = iata
        self.entity_name = entity_name
        self._auth = (settings.companies_house_api_key, "")

    def _get_airport_id(self, db: Session):
        if not self.iata:
            return None
        a = db.query(Airport).filter_by(iata_code=self.iata).first()
        return a.id if a else None

    def fetch(self) -> dict:
        if not settings.companies_house_api_key:
            raise RuntimeError(
                "COMPANIES_HOUSE_API_KEY not configured — Companies House requires auth."
            )

        profile_url = f"{API_BASE}/company/{self.company_number}"
        psc_url = f"{API_BASE}/company/{self.company_number}/persons-with-significant-control"

        profile_resp = httpx.get(profile_url, auth=self._auth, timeout=15)
        profile_resp.raise_for_status()

        # PSC can legitimately 404 (company has no declared controllers) — that's fine.
        psc_data: dict = {}
        psc_resp = httpx.get(psc_url, auth=self._auth, timeout=15)
        if psc_resp.status_code == 200:
            psc_data = psc_resp.json()
        elif psc_resp.status_code not in (404,):
            psc_resp.raise_for_status()

        return {"profile": profile_resp.json(), "psc": psc_data, "url": profile_url}

    def parse(self, raw: dict) -> list[RawRecord]:
        retrieved_at = datetime.now(timezone.utc)
        records = []

        profile = raw["profile"]
        source_url = raw["url"]

        # Company profile record
        records.append(RawRecord(
            entity_key=f"ch:{self.company_number}:profile",
            source_url=source_url,
            source_document_id=self.company_number,
            retrieved_at=retrieved_at,
            record_type="OWNERSHIP",
            payload={
                "company_number": self.company_number,
                "company_name": profile.get("company_name"),
                "company_status": profile.get("company_status"),
                "company_type": profile.get("type"),
                "date_of_creation": profile.get("date_of_creation"),
                "jurisdiction": profile.get("jurisdiction"),
                "registered_office": profile.get("registered_office_address", {}),
                "sic_codes": profile.get("sic_codes", []),
                "accounts": profile.get("accounts", {}),
                "confirmation_statement": profile.get("confirmation_statement", {}),
            },
        ))

        # PSC records
        for psc in raw["psc"].get("items", []):
            records.append(RawRecord(
                entity_key=f"ch:{self.company_number}:psc:{psc.get('links', {}).get('self', '')}",
                source_url=f"{API_BASE}/company/{self.company_number}/persons-with-significant-control",
                source_document_id=self.company_number,
                retrieved_at=retrieved_at,
                record_type="OWNERSHIP",
                payload={
                    "company_number": self.company_number,
                    "psc_name": psc.get("name"),
                    "psc_kind": psc.get("kind"),
                    "natures_of_control": psc.get("natures_of_control", []),
                    "notified_on": psc.get("notified_on"),
                    "nationality": psc.get("nationality"),
                    "country_of_residence": psc.get("country_of_residence"),
                },
            ))

        logger.info("%s: parsed %d records (1 profile + %d PSC)", self.entity_name, len(records), len(records) - 1)
        return records

    def run(self, db: Session):
        airport_id = self._get_airport_id(db)
        result = super().run(db)
        if airport_id:
            from backend.models import DataRecord
            (
                db.query(DataRecord)
                .filter(
                    DataRecord.source_id == SOURCE_ID,
                    DataRecord.payload["company_number"].astext == self.company_number,
                    DataRecord.airport_id.is_(None),
                )
                .update({"airport_id": airport_id}, synchronize_session=False)
            )
            db.commit()
        return result


def run_all(db: Session, company_numbers: list[str] | None = None) -> dict:
    targets = {
        cn: info
        for cn, info in KNOWN_ENTITIES.items()
        if company_numbers is None or cn in company_numbers
    }
    totals: dict = {"created": 0, "skipped": 0, "errors": []}
    for cn, (iata, name) in targets.items():
        try:
            ingestor = CompaniesHouseIngestor(company_number=cn, iata=iata, entity_name=name)
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
        # Default: Heathrow Airport Limited only
        company_numbers = sys.argv[1:] or ["01991017"]
        result = run_all(db, company_numbers=company_numbers)
        print(f"Companies House: created={result['created']} skipped={result['skipped']} errors={result['errors']}")
    finally:
        db.close()
