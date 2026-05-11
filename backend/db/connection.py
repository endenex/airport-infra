from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings

if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Configure it in .env (local) or as an "
        "environment variable / repository secret (CI/production)."
    )

# SQLite (used in tests) doesn't support QueuePool params.
_is_sqlite = settings.database_url.startswith("sqlite")
_engine_kwargs: dict = {"pool_pre_ping": True}
if not _is_sqlite:
    _engine_kwargs.update(pool_size=5, max_overflow=10)
else:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
