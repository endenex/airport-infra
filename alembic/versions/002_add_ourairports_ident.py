"""Add ourairports_ident to airports

Revision ID: 002
Revises: 001
Create Date: 2026-05-11

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # OurAirports primary identifier — can be ICAO, FAA, or local code (up to 7 chars)
    # Needed for cross-referencing back to the OurAirports dataset
    op.add_column(
        "airports",
        sa.Column("ourairports_ident", sa.String(10), nullable=True, unique=True),
    )
    op.create_index("ix_airports_ourairports_ident", "airports", ["ourairports_ident"])


def downgrade() -> None:
    op.drop_index("ix_airports_ourairports_ident", "airports")
    op.drop_column("airports", "ourairports_ident")
