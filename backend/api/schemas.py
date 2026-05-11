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


# ── Transactions (Appendix D Layer γ-compatible) ─────────────────────────


class TransactionParty(BaseModel):
    """
    One participant in a transaction — buyer, seller, or rival bidder.
    identifier_status preserves the honest uncertainty about whether the
    party was confirmed, suspected from press leak, or unknown.
    """

    name: str
    role: str | None = Field(default=None, description="lead | co_investor | lp | advisor")
    identifier_status: str = Field(
        default="identified",
        description="identified | suspected | unknown",
    )
    equity_stake_pct: float | None = None
    is_strategic_operator: bool | None = None
    fund_name: str | None = None
    fund_vintage: int | None = Field(default=None, description="Year, e.g. 2018 for MIP IV")
    source_quote: str | None = None


class RivalBid(TransactionParty):
    """A losing or withdrawn bidder. Adds price-confidence metadata."""

    bid_price: float | None = None
    price_confidence: str | None = Field(
        default=None, description="confirmed | rumored | range"
    )
    outcome: str | None = Field(
        default=None, description="lost | withdrew | shortlisted | unknown"
    )


class Transaction(BaseModel):
    """One transaction process — closed or counterfactual."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    airport_id: uuid.UUID | None
    asset_name: str
    announce_date: date | None
    signing_date: date | None
    close_date: date | None
    state: str
    transaction_type: str
    enterprise_value: float | None
    equity_value: float | None
    currency: str | None
    stake_percent: float | None
    price_information_confidence: str | None
    reason_for_failure_status: str | None
    reason_for_failure_text: str | None
    buyer_entities: list[dict[str, Any]] | None
    seller_entities: list[dict[str, Any]] | None
    rival_bids: list[dict[str, Any]] | None
    continuing_holders: list[dict[str, Any]] | None
    source_url: str
    source_document_id: str | None
    retrieved_at: datetime
    methodology_version_id: uuid.UUID
    ingestion_run_id: uuid.UUID | None
    notes: str | None
    created_at: datetime


class TransactionCreate(BaseModel):
    """Manual transaction entry — used for seeding before LLM ingestor lands."""

    airport_id: uuid.UUID | None = None
    asset_name: str = Field(min_length=1, max_length=500)
    announce_date: date | None = None
    signing_date: date | None = None
    close_date: date | None = None
    state: str = Field(description="closed | abandoned | pulled | bid_lost | postponed | rumored")
    transaction_type: str = Field(
        description="acquisition | divestment | refinancing | ipo | concession_award | minority_stake | secondary_buyout | other"
    )
    enterprise_value: float | None = None
    equity_value: float | None = None
    currency: str | None = Field(default=None, max_length=3)
    stake_percent: float | None = Field(default=None, ge=0, le=100)
    price_information_confidence: str | None = Field(
        default=None, description="confirmed | rumored | range | unknown"
    )
    reason_for_failure_status: str | None = Field(
        default=None, description="disclosed | inferred | unknown"
    )
    reason_for_failure_text: str | None = None
    buyer_entities: list[TransactionParty] = Field(default_factory=list)
    seller_entities: list[TransactionParty] = Field(default_factory=list)
    rival_bids: list[RivalBid] = Field(default_factory=list)
    continuing_holders: list[TransactionParty] = Field(default_factory=list)
    source_url: str = Field(min_length=1)
    source_document_id: str | None = None
    notes: str | None = None


class Page(BaseModel, Generic[T]):
    """Standard paginated envelope."""

    items: list[T]
    total: int
    limit: int
    offset: int
