from fastapi import FastAPI

from backend.config import settings

app = FastAPI(
    title="Airport Infrastructure Intelligence Platform",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}
