import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class MethodologyVersion(Base):
    """
    Tracks schema and calculation methodology versions.
    Every data_record references a methodology version so records under
    older methodologies (e.g. pre-CORSIA 2027) are never silently overwritten.
    """

    __tablename__ = "methodology_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_string: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # NULL = currently active version
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    data_records: Mapped[list["DataRecord"]] = relationship(  # noqa: F821
        "DataRecord", back_populates="methodology_version"
    )
