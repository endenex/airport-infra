import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class LLMExtraction(Base):
    """
    Metadata for every LLM-extracted record. Confidence scoring is mandatory —
    records above the threshold auto-populate; below it queue for founder review.
    """

    __tablename__ = "llm_extractions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    data_record_id: Mapped[str] = mapped_column(
        ForeignKey("data_records.id"), nullable=False, unique=True, index=True
    )
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    # auto_approved | pending_review | approved | rejected
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending_review", index=True
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Full LLM response stored for debugging and prompt iteration
    raw_llm_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    data_record: Mapped["DataRecord"] = relationship(  # noqa: F821
        "DataRecord", back_populates="llm_extraction"
    )
