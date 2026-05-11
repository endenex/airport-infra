"""Add lifecycle position metadata to airports + seed methodology v1.1.0

Revision ID: 003
Revises: 002
Create Date: 2026-05-11

Implements Layer α of Appendix D — Concession Lifecycle Position.
Lifecycle is metadata on the airport entity (per appendix implementation
note), with the methodology version and computed inputs stored alongside
the output so classifications can be defended.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "airports",
        sa.Column("lifecycle_stage", sa.String(20), nullable=True),
    )
    op.add_column(
        "airports",
        sa.Column(
            "lifecycle_methodology_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("methodology_versions.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "airports",
        sa.Column("lifecycle_inputs", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "airports",
        sa.Column("lifecycle_computed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_airports_lifecycle_stage", "airports", ["lifecycle_stage"])

    # Seed methodology version 1.1.0 — Lifecycle Position v1.
    # The thresholds match Appendix D's initial framework. The regulated-
    # airport-as-concession-proxy approach is documented in the description
    # so future versions can refine it without losing the audit trail.
    op.execute(
        """
        INSERT INTO methodology_versions (id, version_string, description, effective_from)
        VALUES (
            gen_random_uuid(),
            '1.1.0',
            'Lifecycle Position v1 (Appendix D Layer α). '
            'For fixed-term concessions, uses concession award/expiry dates. '
            'For continuously-regulated airports (Heathrow, AENA, ADP, etc.), '
            'uses the current regulatory period as a proxy for "concession period". '
            'Capex completion derived from forecast capex when actuals are not yet '
            'ingested. Debt amortisation and dividend trajectory inputs marked '
            'null when source data is unavailable. Thresholds: '
            'late = horizon < 30% OR debt amort > 70%; '
            'early = capex < 30% AND debt < 20% AND horizon > 70%; '
            'mid = 30%-70% capex; indeterminate otherwise.',
            NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM methodology_versions WHERE version_string = '1.1.0'")
    op.drop_index("ix_airports_lifecycle_stage", "airports")
    op.drop_column("airports", "lifecycle_computed_at")
    op.drop_column("airports", "lifecycle_inputs")
    op.drop_column("airports", "lifecycle_methodology_version_id")
    op.drop_column("airports", "lifecycle_stage")
