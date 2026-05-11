"""Add continuing_holders column to transactions table

Revision ID: 005
Revises: 004
Create Date: 2026-05-11

Companion to transaction-extraction prompt v1.1. The "stake-change rule"
distinguishes parties whose stake CHANGED in the transaction (buyers,
sellers) from parties who continue to hold a position UNCHANGED through
the deal (continuing holders). The latter belong in their own bucket — not
in buyer_entities (they didn't acquire) and not in seller_entities (they
didn't sell). Each entry follows the shape:

  {"name": str,
   "identifier_status": "identified" | "suspected" | "unknown",
   "post_transaction_stake_pct": float | null,
   "source_quote": str | null}
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("continuing_holders", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "continuing_holders")
