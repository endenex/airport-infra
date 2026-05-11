"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "methodology_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version_string", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "assumption_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
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

    op.create_table(
        "airports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("iata_code", sa.String(3), unique=True, nullable=True),
        sa.Column("icao_code", sa.String(4), unique=True, nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("city", sa.String(255), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("tier", sa.Integer, nullable=True),
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

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("records_fetched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_ingestion_runs_source_id", "ingestion_runs", ["source_id"])

    op.create_table(
        "data_records",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "airport_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("airports.id"),
            nullable=True,
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_document_id", sa.String(500), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "methodology_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("methodology_versions.id"),
            nullable=False,
        ),
        sa.Column("record_type", sa.String(50), nullable=False),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("calculation_lineage", postgresql.JSONB, nullable=True),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_data_records_airport_id", "data_records", ["airport_id"])
    op.create_index("ix_data_records_source_id", "data_records", ["source_id"])
    op.create_index("ix_data_records_record_type", "data_records", ["record_type"])
    op.create_index(
        "ix_data_records_methodology_version_id", "data_records", ["methodology_version_id"]
    )

    op.create_table(
        "llm_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "data_record_id",
            sa.String(100),
            sa.ForeignKey("data_records.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("confidence_score", sa.Float, nullable=False),
        sa.Column(
            "review_status",
            sa.String(20),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column("review_notes", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_llm_response", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_llm_extractions_confidence_score", "llm_extractions", ["confidence_score"]
    )
    op.create_index("ix_llm_extractions_review_status", "llm_extractions", ["review_status"])

    op.create_table(
        "cross_validations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "primary_record_id",
            sa.String(100),
            sa.ForeignKey("data_records.id"),
            nullable=False,
        ),
        sa.Column(
            "comparison_record_id",
            sa.String(100),
            sa.ForeignKey("data_records.id"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("primary_value", postgresql.JSONB, nullable=True),
        sa.Column("comparison_value", postgresql.JSONB, nullable=True),
        sa.Column("agreement", sa.Boolean, nullable=False),
        sa.Column("discrepancy_pct", sa.Float, nullable=True),
        sa.Column("flagged_for_review", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_cross_validations_primary_record_id",
        "cross_validations",
        ["primary_record_id"],
    )

    # Seed: methodology version 1.0.0 — baseline before CORSIA 2027 / ReFuelEU phases
    op.execute(
        """
        INSERT INTO methodology_versions (id, version_string, description, effective_from)
        VALUES (
            gen_random_uuid(),
            '1.0.0',
            'Baseline methodology. Pre-CORSIA 2027, pre-ReFuelEU phase 2. '
            'All records created before regulatory transition points reference this version.',
            NOW()
        )
        """
    )

    # Seed: default assumption set
    op.execute(
        """
        INSERT INTO assumption_sets (id, name, description, parameters, is_default, created_by)
        VALUES (
            gen_random_uuid(),
            'Platform Default',
            'Default platform assumption set. Override per-calculation as needed.',
            '{
                "cost_of_debt_pct": 4.5,
                "traffic_recovery_years": 3,
                "inflation_pct": 2.5,
                "terminal_growth_rate_pct": 2.0
            }',
            true,
            'system'
        )
        """
    )


def downgrade() -> None:
    op.drop_table("cross_validations")
    op.drop_table("llm_extractions")
    op.drop_table("data_records")
    op.drop_table("ingestion_runs")
    op.drop_table("airports")
    op.drop_table("assumption_sets")
    op.drop_table("methodology_versions")
