import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.data_record import DataRecord
    from backend.models.methodology_version import MethodologyVersion


class Airport(Base):
    """
    Master entity table. One row per airport in the coverage universe.
    Populated initially from OurAirports CSV (Week 2), enriched by every
    subsequent ingestor. Coverage tier per §4 of the brief.
    """

    __tablename__ = "airports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    iata_code: Mapped[str | None] = mapped_column(String(3), unique=True, nullable=True)
    icao_code: Mapped[str | None] = mapped_column(String(4), unique=True, nullable=True)
    # OurAirports primary identifier — ICAO, FAA, or local code (up to 7 chars)
    ourairports_ident: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Coverage tier 1-5 per §4 of the brief
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Lifecycle Position metadata (Appendix D Layer α) ──────────────────
    # "early" | "mid" | "late" | "indeterminate"
    lifecycle_stage: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # FK to the methodology_version used to compute this stage. Thresholds
    # will evolve — storing the version lets us defend historical classifications.
    lifecycle_methodology_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("methodology_versions.id"), nullable=True
    )
    # Inputs to the computation (horizon %, capex %, debt %, etc.) plus
    # methodology notes (e.g. "regulated airport — used H7 period as proxy").
    # Stored so customers who challenge the classification can see what fed it.
    lifecycle_inputs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    lifecycle_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    data_records: Mapped[list["DataRecord"]] = relationship(
        "DataRecord", back_populates="airport"
    )
    lifecycle_methodology_version: Mapped["MethodologyVersion | None"] = relationship(
        "MethodologyVersion", foreign_keys=[lifecycle_methodology_version_id]
    )
