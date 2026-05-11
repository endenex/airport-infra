import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class DataRecord(Base):
    """
    Core provenance table. Every piece of data stored on the platform lives here.

    Primary key is deterministic: sha256(source_id + retrieval_date + content_hash)[:48]
    This makes ingestion idempotent — re-running against the same source produces
    the same IDs and INSERT ON CONFLICT DO NOTHING skips duplicates.

    Record types: FINANCIAL | OPERATIONAL | CLIMATE | CONCESSION | OWNERSHIP | TRANSACTION
    """

    __tablename__ = "data_records"

    # Deterministic content-addressed ID — see ingestion.base.record_id()
    id: Mapped[str] = mapped_column(String(100), primary_key=True)

    airport_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("airports.id"), nullable=True, index=True
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # ── Provenance (non-negotiable per §8) ───────────────────────────────────
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ── Methodology versioning (non-negotiable per §8) ───────────────────────
    methodology_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("methodology_versions.id"), nullable=False, index=True
    )

    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Core payload — structured fields vary by record_type
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # For derived/calculated values: ordered list of {step, source_record_ids, formula}
    # NULL for raw ingested values
    calculation_lineage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    airport: Mapped["Airport | None"] = relationship(  # noqa: F821
        "Airport", back_populates="data_records"
    )
    methodology_version: Mapped["MethodologyVersion"] = relationship(  # noqa: F821
        "MethodologyVersion", back_populates="data_records"
    )
    ingestion_run: Mapped["IngestionRun | None"] = relationship(  # noqa: F821
        "IngestionRun", back_populates="data_records"
    )
    llm_extraction: Mapped["LLMExtraction | None"] = relationship(  # noqa: F821
        "LLMExtraction", back_populates="data_record", uselist=False
    )
    cross_validations_primary: Mapped[list["CrossValidation"]] = relationship(  # noqa: F821
        "CrossValidation",
        foreign_keys="CrossValidation.primary_record_id",
        back_populates="primary_record",
    )
