"""Create transactions table with counterfactual schema baked in

Revision ID: 004
Revises: 003
Create Date: 2026-05-11

Per Appendix D Layer γ (locked decision #19): counterfactual records share
the transaction schema. They are NOT a separate table — they are
transactions with state in {abandoned, pulled, bid_lost, postponed}. So
state, rival-bidder status, reason-for-failure status, and price-info
confidence are first-class columns from day one.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # ── Subject (asset being transacted) ───────────────────────────────
        # airport_id nullable: some deals span a portfolio (e.g. "Vinci
        # acquires Aéroports d'Algarve portfolio"); asset_name captures the
        # human-readable target regardless.
        sa.Column(
            "airport_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("airports.id"),
            nullable=True,
        ),
        sa.Column("asset_name", sa.String(500), nullable=False),

        # ── Timing ─────────────────────────────────────────────────────────
        sa.Column("announce_date", sa.Date, nullable=True),
        sa.Column("signing_date", sa.Date, nullable=True),
        sa.Column("close_date", sa.Date, nullable=True),

        # ── State (Appendix D Layer γ) ─────────────────────────────────────
        # closed | abandoned | pulled | bid_lost | postponed | rumored
        sa.Column("state", sa.String(20), nullable=False),

        # acquisition | divestment | refinancing | ipo | concession_award
        # | minority_stake | other
        sa.Column("transaction_type", sa.String(50), nullable=False),

        # ── Economic terms ─────────────────────────────────────────────────
        sa.Column("enterprise_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("equity_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),  # ISO 4217
        sa.Column("stake_percent", sa.Float, nullable=True),  # 0-100

        # Price confidence flag — confirmed | rumored | range | unknown
        sa.Column("price_information_confidence", sa.String(20), nullable=True),

        # ── Failure attribution (for abandoned / pulled / postponed) ──────
        sa.Column("reason_for_failure_status", sa.String(20), nullable=True),
        # disclosed | inferred | unknown
        sa.Column("reason_for_failure_text", sa.Text, nullable=True),

        # ── Party data (JSONB lists of structured entries) ─────────────────
        # Each entry carries identifier_status (identified | suspected |
        # unknown) so rumoured bidders never get asserted as confirmed.
        # Schema documented in backend/api/schemas.py.
        sa.Column("buyer_entities", postgresql.JSONB, nullable=True),
        sa.Column("seller_entities", postgresql.JSONB, nullable=True),
        sa.Column("rival_bids", postgresql.JSONB, nullable=True),

        # ── Provenance (non-negotiable, same discipline as DataRecord) ────
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_document_id", sa.String(500), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "methodology_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("methodology_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id"),
            nullable=True,
        ),

        sa.Column("notes", sa.Text, nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_transactions_airport_id", "transactions", ["airport_id"])
    op.create_index("ix_transactions_state", "transactions", ["state"])
    op.create_index("ix_transactions_transaction_type", "transactions", ["transaction_type"])
    op.create_index("ix_transactions_announce_date", "transactions", ["announce_date"])
    op.create_index("ix_transactions_close_date", "transactions", ["close_date"])


def downgrade() -> None:
    op.drop_index("ix_transactions_close_date", "transactions")
    op.drop_index("ix_transactions_announce_date", "transactions")
    op.drop_index("ix_transactions_transaction_type", "transactions")
    op.drop_index("ix_transactions_state", "transactions")
    op.drop_index("ix_transactions_airport_id", "transactions")
    op.drop_table("transactions")
