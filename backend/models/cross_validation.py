import uuid
from datetime import datetime

from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class CrossValidation(Base):
    """
    Records cross-source validation results (e.g. XBRL vs PDF extraction,
    multiple news sources for the same transaction). Conflicts are flagged
    for founder review rather than silently resolved.
    """

    __tablename__ = "cross_validations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    primary_record_id: Mapped[str] = mapped_column(
        ForeignKey("data_records.id"), nullable=False, index=True
    )
    comparison_record_id: Mapped[str] = mapped_column(
        ForeignKey("data_records.id"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    comparison_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    agreement: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # For numeric fields: abs((primary - comparison) / primary)
    discrepancy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    flagged_for_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    primary_record: Mapped["DataRecord"] = relationship(  # noqa: F821
        "DataRecord",
        foreign_keys=[primary_record_id],
        back_populates="cross_validations_primary",
    )
    comparison_record: Mapped["DataRecord"] = relationship(  # noqa: F821
        "DataRecord",
        foreign_keys=[comparison_record_id],
    )
