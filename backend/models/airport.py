import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    data_records: Mapped[list["DataRecord"]] = relationship(  # noqa: F821
        "DataRecord", back_populates="airport"
    )
