"""
Test configuration. Uses an in-memory SQLite database so tests run without
a real Postgres connection. SQLAlchemy models are created fresh per session.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from backend.models import Base, MethodologyVersion, AssumptionSet


@pytest.fixture(scope="session")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()

    # Seed: methodology version 1.0.0
    version = MethodologyVersion(
        version_string="1.0.0",
        description="Test baseline methodology",
    )
    session.add(version)

    # Seed: default assumption set
    assumption_set = AssumptionSet(
        name="Test Default",
        parameters={"cost_of_debt_pct": 4.5, "inflation_pct": 2.5},
        is_default=True,
    )
    session.add(assumption_set)
    session.commit()

    yield session
    session.close()
