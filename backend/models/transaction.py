"""
Transaction model — Appendix D Layer γ (Counterfactual) compatible schema.

One row = one process, not one bidder. Closed deals carry the winner in
buyer_entities and losing bidders in rival_bids. Abandoned / pulled /
postponed deals carry state + reason_for_failure_* and may carry rumoured
parties with identifier_status="suspected" or "unknown".

This single-table design is locked by Appendix D #19: "Counterfactual
records share the transaction schema. They're not a separate table;
they're transactions with state = abandoned/pulled/bid-lost."
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.airport import Airport
    from backend.models.ingestion_run import IngestionRun
    from backend.models.methodology_version import MethodologyVersion


# State + transaction_type are stored as strings (not enums) so the schema
# can grow without a migration each time the lexicon expands. The canonical
# values are documented here and enforced at the Pydantic schema layer.
VALID_STATES = {"closed", "abandoned", "pulled", "bid_lost", "postponed", "rumored"}
VALID_TRANSACTION_TYPES = {
    "acquisition", "divestment", "refinancing", "ipo",
    "concession_award", "minority_stake", "secondary_buyout", "other",
}
VALID_PRICE_CONFIDENCE = {"confirmed", "rumored", "range", "unknown"}
VALID_FAILURE_STATUS = {"disclosed", "inferred", "unknown"}


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # ── Subject ──────────────────────────────────────────────────────────
    airport_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("airports.id"), nullable=True, index=True
    )
    asset_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # ── Timing ───────────────────────────────────────────────────────────
    announce_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    signing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    close_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # ── State (Layer γ) ──────────────────────────────────────────────────
    state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # ── Economic terms ───────────────────────────────────────────────────
    # Numeric for precision — these can be in any currency unit (the
    # `currency` column qualifies). Stored "as reported" — no auto-FX.
    enterprise_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    equity_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    stake_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_information_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Failure attribution ──────────────────────────────────────────────
    reason_for_failure_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason_for_failure_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Parties (JSONB lists of structured entries) ──────────────────────
    # Each entry follows the shape:
    #   {"name": str,
    #    "role": "lead" | "co_investor" | "lp" | "advisor",
    #    "identifier_status": "identified" | "suspected" | "unknown",
    #    "equity_stake_pct": float | null,
    #    "is_strategic_operator": bool | null,
    #    "fund_name": str | null,
    #    "fund_vintage": int | null,  (e.g. 2018 for MIP IV)
    #    "source_quote": str | null}
    # rival_bids additionally carries {"bid_price": float | null,
    #   "price_confidence": "confirmed" | "rumored" | "range",
    #   "outcome": "lost" | "withdrew" | "shortlisted"}
    buyer_entities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    seller_entities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rival_bids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Provenance ───────────────────────────────────────────────────────
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    methodology_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("methodology_versions.id"), nullable=False, index=True
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ── Relationships ────────────────────────────────────────────────────
    airport: Mapped["Airport | None"] = relationship("Airport", foreign_keys=[airport_id])
    methodology_version: Mapped["MethodologyVersion"] = relationship(
        "MethodologyVersion", foreign_keys=[methodology_version_id]
    )
    ingestion_run: Mapped["IngestionRun | None"] = relationship(
        "IngestionRun", foreign_keys=[ingestion_run_id]
    )
