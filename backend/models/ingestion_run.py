import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class IngestionRun(Base):
    """Audit trail for every ingestor execution."""

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # running | completed | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Idempotency: records skipped because they already existed with same ID
    records_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    data_records: Mapped[list["DataRecord"]] = relationship(  # noqa: F821
        "DataRecord", back_populates="ingestion_run"
    )
