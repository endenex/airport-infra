"""
Pydantic response models for the FastAPI surface.

These mirror the SQLAlchemy models but only expose what callers should see.
Internal IDs and FKs flow through; secrets and noisy debug payloads don't.
"""

import uuid
from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class AirportRef(BaseModel):
    """Minimal airport reference for embedding in other resources."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    iata_code: str | None
    icao_code: str | None
    name: str
    country_code: str | None


class LifecyclePosition(BaseModel):
    """Concession Lifecycle Position metadata (Appendix D Layer α)."""

    model_config = ConfigDict(from_attributes=True)

    stage: str | None  # "early" | "mid" | "late" | "indeterminate"
    methodology_version: str | None  # e.g. "1.1.0"
    computed_at: datetime | None
    inputs: dict[str, Any] | None


class Airport(AirportRef):
    """Full airport row."""

    ourairports_ident: str | None
    city: str | None
    latitude: float | None
    longitude: float | None
    tier: int | None
    created_at: datetime
    updated_at: datetime


class AirportSummary(Airport):
    """Airport with rolled-up record counts. Used on detail endpoint."""

    records_total: int
    records_by_type: dict[str, int]
    lifecycle: LifecyclePosition | None


class DataRecord(BaseModel):
    """One row of provenanced data."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    airport_id: uuid.UUID | None
    source_id: str
    source_url: str
    source_document_id: str | None
    retrieved_at: datetime
    methodology_version_id: uuid.UUID
    record_type: str
    period_start: date | None
    period_end: date | None
    payload: dict[str, Any]
    calculation_lineage: dict[str, Any] | None
    ingestion_run_id: uuid.UUID | None
    created_at: datetime


class IngestionRun(BaseModel):
    """Audit row for an ingestor execution."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str  # running | completed | failed
    records_fetched: int
    records_created: int
    records_skipped: int
    error_message: str | None


class LLMExtraction(BaseModel):
    """LLM extraction metadata. Hydrated with linked DataRecord for review."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    data_record_id: str
    model_id: str
    prompt_version: str
    confidence_score: float
    review_status: str  # auto_approved | pending_review | approved | rejected
    review_notes: str | None
    reviewed_at: datetime | None
    raw_llm_response: dict[str, Any] | None
    created_at: datetime


class LLMExtractionWithRecord(LLMExtraction):
    """Review-queue row — the extraction plus the underlying record."""

    data_record: DataRecord


class ReviewDecision(BaseModel):
    """Body for approving / rejecting a pending LLM extraction."""

    notes: str | None = Field(default=None, max_length=2000)


class Page(BaseModel, Generic[T]):
    """Standard paginated envelope."""

    items: list[T]
    total: int
    limit: int
    offset: int
