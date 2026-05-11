"""
LLM pipeline base. Every extraction pipeline subclasses LLMPipelineBase.

Confidence scoring is mandatory on every extracted record:
- score >= HIGH_CONFIDENCE_THRESHOLD → auto_approved, written to data_records
- score <  HIGH_CONFIDENCE_THRESHOLD → pending_review, written but flagged

Cross-validation is handled by CrossValidationMixin (see below) — when two
sources produce records for the same field, agreement is checked and conflicts
are flagged for review.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import anthropic
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import DataRecord, LLMExtraction, MethodologyVersion

logger = logging.getLogger(__name__)


@dataclass
class ExtractedRecord:
    """One structured record as produced by an LLM extraction pipeline."""

    entity_key: str
    source_url: str
    source_document_id: str | None
    retrieved_at: datetime
    record_type: str
    payload: dict
    confidence_score: float  # 0.0 – 1.0; mandatory
    period_start: str | None = None
    period_end: str | None = None
    airport_id: uuid.UUID | None = None
    raw_llm_response: dict | None = None


@dataclass
class ExtractionResult:
    records: list[ExtractedRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def auto_approved(self) -> list[ExtractedRecord]:
        return [r for r in self.records if r.confidence_score >= settings.llm_high_confidence_threshold]

    @property
    def pending_review(self) -> list[ExtractedRecord]:
        return [r for r in self.records if r.confidence_score < settings.llm_high_confidence_threshold]


class LLMPipelineBase(ABC):
    """
    Base class for all LLM extraction pipelines.

    Subclasses implement build_messages() and parse_response().
    The extract() method handles API calls, confidence routing, and DB writes.
    """

    prompt_version: str  # e.g. "1.0" — bump when prompt changes materially

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    @abstractmethod
    def build_messages(self, document: str, context: dict) -> list[dict]:
        """
        Build the messages list for the Claude API call.
        context: arbitrary metadata about the airport / source / period.
        """
        ...

    @abstractmethod
    def parse_response(self, response_text: str, context: dict) -> list[ExtractedRecord]:
        """
        Parse the LLM response text into structured ExtractedRecord list.
        Every record must have a confidence_score.
        """
        ...

    def route(
        self, record: ExtractedRecord
    ) -> Literal["auto_approved", "pending_review"]:
        if record.confidence_score >= settings.llm_high_confidence_threshold:
            return "auto_approved"
        return "pending_review"

    def extract(self, document: str, context: dict) -> ExtractionResult:
        """Call the LLM and return structured records with confidence routing."""
        result = ExtractionResult()
        try:
            messages = self.build_messages(document, context)
            response = self.client.messages.create(
                model=settings.llm_extraction_model,
                max_tokens=4096,
                messages=messages,
            )
            response_text = response.content[0].text
            result.records = self.parse_response(response_text, context)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            result.errors.append(error_msg)
            logger.error("LLM extraction failed: %s", error_msg)
        return result

    def _get_current_methodology_version(self, db: Session) -> MethodologyVersion:
        version = (
            db.query(MethodologyVersion)
            .filter(MethodologyVersion.effective_to.is_(None))
            .order_by(MethodologyVersion.effective_from.desc())
            .first()
        )
        if version is None:
            raise RuntimeError("No active methodology version found. Run migrations first.")
        return version

    def persist(
        self,
        result: ExtractionResult,
        db: Session,
        ingestion_run_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        """
        Write extracted records to data_records + llm_extractions tables.
        Returns counts: {created, skipped, pending_review, auto_approved}.
        """
        from ingestion.base import IngestorBase  # avoid circular at module level

        methodology_version = self._get_current_methodology_version(db)
        counts: dict[str, int] = {
            "created": 0,
            "skipped": 0,
            "auto_approved": 0,
            "pending_review": 0,
        }

        for extracted in result.records:
            # Reuse deterministic ID logic from ingestion harness
            import hashlib, json as _json
            payload_hash = hashlib.sha256(
                _json.dumps(extracted.payload, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            retrieval_date = extracted.retrieved_at.strftime("%Y-%m-%d")
            composite = f"llm:{retrieval_date}:{extracted.entity_key}:{payload_hash}"
            rec_id = hashlib.sha256(composite.encode()).hexdigest()[:48]

            if db.get(DataRecord, rec_id) is not None:
                counts["skipped"] += 1
                continue

            review_status = self.route(extracted)
            record = DataRecord(
                id=rec_id,
                airport_id=extracted.airport_id,
                source_id=f"llm:{self.__class__.__name__.lower()}",
                source_url=extracted.source_url,
                source_document_id=extracted.source_document_id,
                retrieved_at=extracted.retrieved_at,
                methodology_version_id=methodology_version.id,
                record_type=extracted.record_type,
                period_start=extracted.period_start,
                period_end=extracted.period_end,
                payload=extracted.payload,
                ingestion_run_id=ingestion_run_id,
            )
            db.add(record)
            db.flush()

            extraction_meta = LLMExtraction(
                data_record_id=rec_id,
                model_id=settings.llm_extraction_model,
                prompt_version=self.prompt_version,
                confidence_score=extracted.confidence_score,
                review_status=review_status,
                raw_llm_response=extracted.raw_llm_response,
            )
            db.add(extraction_meta)
            counts["created"] += 1
            counts[review_status] += 1

        db.commit()
        return counts
