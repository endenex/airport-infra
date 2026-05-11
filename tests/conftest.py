"""
Test configuration. Uses an in-memory SQLite database so tests run without
a real Postgres connection. SQLAlchemy models are created fresh per session.
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models import (
    Airport,
    AssumptionSet,
    Base,
    DataRecord,
    IngestionRun,
    LLMExtraction,
    MethodologyVersion,
)


# SQLite can't compile JSONB. Map it to plain JSON for tests — production
# stays on PostgreSQL JSONB; this only kicks in under the sqlite dialect.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture(scope="session")
def engine():
    # StaticPool keeps a single underlying connection for the whole session
    # so every test session (and the API TestClient) sees the same in-memory
    # database. Without it, sqlite:///:memory: gives each new connection its
    # own empty DB.
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite doesn't enforce FK constraints by default
    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture(scope="session")
def db_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)  # noqa: N806
    session = SessionLocal()

    # Seed only if missing — api_db (function-scoped) may have run first
    # and already inserted the baseline methodology row.
    if session.query(MethodologyVersion).count() == 0:
        session.add(MethodologyVersion(
            version_string="1.0.0", description="Test baseline methodology"
        ))
        session.commit()

    if session.query(AssumptionSet).count() == 0:
        session.add(AssumptionSet(
            name="Test Default",
            parameters={"cost_of_debt_pct": 4.5, "inflation_pct": 2.5},
            is_default=True,
        ))
        session.commit()

    yield session
    session.close()


# ── API test fixtures ────────────────────────────────────────────────────


@pytest.fixture
def api_db(engine):
    """
    Per-test session with a clean slate for data tables. Preserves the
    session-scoped seed of methodology_versions / assumption_sets that
    db_session created — those are reference data, not test fixtures.
    """
    # Tables we wipe between API tests — the "data" tables that hold
    # per-test fixtures. methodology_versions and assumption_sets are
    # seeded once in db_session and are FK targets, so leave them alone.
    DATA_TABLES = (  # noqa: N806
        "cross_validations",
        "llm_extractions",
        "data_records",
        "ingestion_runs",
        "airports",
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)  # noqa: N806
    session = SessionLocal()

    for table_name in DATA_TABLES:
        session.execute(Base.metadata.tables[table_name].delete())
    session.commit()

    # Ensure a methodology_version exists. It usually does (from db_session),
    # but if test ordering puts an api test first, db_session hasn't run yet.
    if session.query(MethodologyVersion).count() == 0:
        session.add(MethodologyVersion(
            version_string="1.0.0", description="test baseline methodology"
        ))
        session.commit()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def api_client(api_db):
    """FastAPI TestClient wired to the per-test isolated session."""
    # Import here so the engine fixture has already registered the JSONB compiler.
    from backend.db.connection import get_db
    from backend.main import app

    def _override_get_db():
        try:
            yield api_db
        finally:
            pass  # session lifecycle is owned by api_db fixture

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_data(api_db):
    """
    Seed a small but realistic set: 3 airports, 2 ingestion runs, 4 records
    (1 FINANCIAL + 1 CLIMATE for LHR, 1 OWNERSHIP for LGW, 1 untyped for an
    airport with no data linkage), plus 1 LLM extraction in pending_review.
    """
    mv = api_db.query(MethodologyVersion).first()
    assert mv is not None  # seeded above

    lhr = Airport(id=uuid.uuid4(), iata_code="LHR", icao_code="EGLL",
                  ourairports_ident="EGLL", name="London Heathrow",
                  country_code="GB", city="London", tier=1)
    lgw = Airport(id=uuid.uuid4(), iata_code="LGW", icao_code="EGKK",
                  ourairports_ident="EGKK", name="London Gatwick",
                  country_code="GB", city="London", tier=2)
    cdg = Airport(id=uuid.uuid4(), iata_code="CDG", icao_code="LFPG",
                  ourairports_ident="LFPG", name="Charles de Gaulle",
                  country_code="FR", city="Paris", tier=1)
    api_db.add_all([lhr, lgw, cdg])
    api_db.flush()

    esma_run = IngestionRun(
        id=uuid.uuid4(), source_id="esma_xbrl", status="completed",
        completed_at=datetime.now(timezone.utc),
        records_fetched=10, records_created=10, records_skipped=0,
    )
    ch_run = IngestionRun(
        id=uuid.uuid4(), source_id="companies_house", status="failed",
        completed_at=datetime.now(timezone.utc),
        records_fetched=0, records_created=0, records_skipped=0,
        error_message="auth failed",
    )
    api_db.add_all([esma_run, ch_run])
    api_db.flush()

    retrieved = datetime.now(timezone.utc)
    rec_lhr_fin = DataRecord(
        id="rec_lhr_fin_01" + "0" * 35, airport_id=lhr.id, source_id="esma_xbrl",
        source_url="https://example.com/lhr.xbrl", source_document_id="doc-1",
        retrieved_at=retrieved, methodology_version_id=mv.id,
        record_type="FINANCIAL", period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
        payload={"concept": "ifrs-full:Revenue", "value": 3500000000.0, "unit": "GBP"},
        ingestion_run_id=esma_run.id,
    )
    rec_lhr_climate = DataRecord(
        id="rec_lhr_clim_01" + "0" * 34, airport_id=lhr.id, source_id="llm:climate",
        source_url="https://example.com/lhr_sust.pdf", source_document_id="doc-2",
        retrieved_at=retrieved, methodology_version_id=mv.id,
        record_type="CLIMATE", period_end=date(2024, 12, 31),
        payload={"concept": "scope_1_emissions_tco2e", "value": 26000.0, "unit": "tCO2e"},
    )
    rec_lgw_own = DataRecord(
        id="rec_lgw_own_01" + "0" * 35, airport_id=lgw.id, source_id="companies_house",
        source_url="https://example.com/lgw_profile", source_document_id="01991018",
        retrieved_at=retrieved, methodology_version_id=mv.id,
        record_type="OWNERSHIP",
        payload={"company_number": "01991018", "company_name": "Gatwick Airport Limited"},
    )
    api_db.add_all([rec_lhr_fin, rec_lhr_climate, rec_lgw_own])
    api_db.flush()

    pending_extraction = LLMExtraction(
        id=uuid.uuid4(), data_record_id=rec_lhr_climate.id,
        model_id="claude-haiku-4-5-20251001", prompt_version="1.0",
        confidence_score=0.72, review_status="pending_review",
        raw_llm_response={"evidence_quote": "scope 1 was 26,000 tCO2e"},
    )
    api_db.add(pending_extraction)
    api_db.commit()

    return {
        "lhr": lhr, "lgw": lgw, "cdg": cdg,
        "esma_run": esma_run, "ch_run": ch_run,
        "rec_lhr_fin": rec_lhr_fin, "rec_lhr_climate": rec_lhr_climate,
        "rec_lgw_own": rec_lgw_own,
        "pending_extraction": pending_extraction,
    }
