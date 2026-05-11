from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import airports, ingestion, records, review, transactions, validations
from backend.config import settings

app = FastAPI(
    title="Airport Infrastructure Intelligence Platform",
    description=(
        "Internal data API for institutional infrastructure investors, "
        "strategic operators, and specialist consultancies. "
        "Three lenses (B/C/D), seven analytical surfaces, full provenance."
    ),
    version="0.1.0",
    # Keep docs open in all environments for now — no public deployment yet.
    docs_url="/docs",
    redoc_url="/redoc",
)

# Permissive CORS for local development. Tighten before going public.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


app.include_router(airports.router)
app.include_router(records.router)
app.include_router(ingestion.router)
app.include_router(review.router)
app.include_router(validations.router)
app.include_router(transactions.router)
