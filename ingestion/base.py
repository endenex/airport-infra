"""
Ingestion base harness. Every ingestor subclasses IngestorBase.

Key guarantees:
- Idempotent: re-running against same source yields same record IDs.
  INSERT ON CONFLICT DO NOTHING skips duplicates; records_skipped is incremented.
- Provenance: every record stores source_url, source_document_id, retrieved_at.
- Methodology version: every record references the current active methodology version.
"""

import hashlib
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models import DataRecord, IngestionRun, MethodologyVersion

logger = logging.getLogger(__name__)


@dataclass
class RawRecord:
    """A single record as produced by an ingestor's parse() method."""

    # Stable identifier within the source (e.g. LEI, CIK, IATA code)
    entity_key: str
    source_url: str
    source_document_id: str | None
    retrieved_at: datetime
    record_type: str  # FINANCIAL | OPERATIONAL | CLIMATE | CONCESSION | OWNERSHIP | TRANSACTION
    payload: dict
    period_start: str | None = None  # ISO date string
    period_end: str | None = None
    airport_id: uuid.UUID | None = None
    # For derived values — leave None for raw ingested records
    calculation_lineage: dict | None = None


@dataclass
class IngestionResult:
    source_id: str
    records_fetched: int = 0
    records_created: int = 0
    records_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class IngestorBase(ABC):
    """
    Base class for all data ingestors.

    Subclasses implement fetch() and parse(). The run() method handles
    IngestionRun creation, idempotency checking, provenance recording,
    and error handling.
    """

    source_id: str  # must match /data/sources/{source_id}.json

    def record_id(self, raw: RawRecord) -> str:
        """
        Deterministic record ID: sha256(source_id + retrieval_date + entity_key + payload_hash).
        Same source + same date + same content = same ID, ensuring idempotency.
        """
        payload_hash = hashlib.sha256(
            json.dumps(raw.payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        retrieval_date = raw.retrieved_at.strftime("%Y-%m-%d")
        composite = f"{self.source_id}:{retrieval_date}:{raw.entity_key}:{payload_hash}"
        return hashlib.sha256(composite.encode()).hexdigest()[:48]

    @abstractmethod
    def fetch(self) -> Any:
        """Fetch raw data from source. Must not modify any state."""
        ...

    @abstractmethod
    def parse(self, raw: Any) -> list[RawRecord]:
        """Transform raw source data into normalised RawRecord list."""
        ...

    def _get_current_methodology_version(self, db: Session) -> MethodologyVersion:
        """Return the currently active methodology version (effective_to IS NULL)."""
        version = (
            db.query(MethodologyVersion)
            .filter(MethodologyVersion.effective_to.is_(None))
            .order_by(MethodologyVersion.effective_from.desc())
            .first()
        )
        if version is None:
            raise RuntimeError(
                "No active methodology version found. Run migrations first (make migrate)."
            )
        return version

    def run(self, db: Session) -> IngestionResult:
        """
        Execute the full ingestion cycle. Creates an IngestionRun record,
        processes all records, and marks the run complete or failed.
        """
        result = IngestionResult(source_id=self.source_id)
        run = IngestionRun(source_id=self.source_id, status="running")
        db.add(run)
        db.flush()

        try:
            methodology_version = self._get_current_methodology_version(db)
            raw_data = self.fetch()
            records = self.parse(raw_data)
            result.records_fetched = len(records)

            # Bulk-fetch existing IDs up-front (one SELECT instead of N db.get() calls).
            # Chunked to keep IN-clause sizes reasonable on PG.
            candidate_ids = [self.record_id(r) for r in records]
            existing_ids: set[str] = set()
            for chunk_start in range(0, len(candidate_ids), 1000):
                chunk = candidate_ids[chunk_start : chunk_start + 1000]
                for (row_id,) in db.query(DataRecord.id).filter(DataRecord.id.in_(chunk)):
                    existing_ids.add(row_id)

            seen_ids: set[str] = set()
            for raw, rec_id in zip(records, candidate_ids):
                # In-memory check covers intra-batch duplicates that db.get() misses
                # for pending (unflushed) objects in the SQLAlchemy identity map.
                if rec_id in seen_ids or rec_id in existing_ids:
                    result.records_skipped += 1
                    continue
                seen_ids.add(rec_id)

                record = DataRecord(
                    id=rec_id,
                    airport_id=raw.airport_id,
                    source_id=self.source_id,
                    source_url=raw.source_url,
                    source_document_id=raw.source_document_id,
                    retrieved_at=raw.retrieved_at,
                    methodology_version_id=methodology_version.id,
                    record_type=raw.record_type,
                    period_start=raw.period_start,
                    period_end=raw.period_end,
                    payload=raw.payload,
                    calculation_lineage=raw.calculation_lineage,
                    ingestion_run_id=run.id,
                )
                db.add(record)
                result.records_created += 1

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.records_fetched = result.records_fetched
            run.records_created = result.records_created
            run.records_skipped = result.records_skipped
            db.commit()

        except Exception as exc:
            db.rollback()
            error_msg = f"{type(exc).__name__}: {exc}"
            result.errors.append(error_msg)
            # Reset counts — the records weren't actually committed.
            result.records_created = 0
            result.records_skipped = 0
            run.status = "failed"
            run.error_message = error_msg
            run.completed_at = datetime.now(timezone.utc)
            db.add(run)
            db.commit()
            logger.error("Ingestion failed for source %s: %s", self.source_id, error_msg)

        logger.info(
            "Ingestion %s: fetched=%d created=%d skipped=%d errors=%d",
            self.source_id,
            result.records_fetched,
            result.records_created,
            result.records_skipped,
            len(result.errors),
        )
        return result
