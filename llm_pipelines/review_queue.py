"""
Review queue helpers. Low-confidence LLM extractions sit in pending_review
status until founder approves or rejects them via these functions.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import LLMExtraction


def list_pending(db: Session, limit: int = 50) -> list[LLMExtraction]:
    return (
        db.query(LLMExtraction)
        .filter(LLMExtraction.review_status == "pending_review")
        .order_by(LLMExtraction.confidence_score.asc())  # lowest confidence first
        .limit(limit)
        .all()
    )


def approve(db: Session, extraction_id: str, notes: str | None = None) -> LLMExtraction:
    extraction = db.get(LLMExtraction, extraction_id)
    if extraction is None:
        raise ValueError(f"LLMExtraction {extraction_id} not found")
    extraction.review_status = "approved"
    extraction.review_notes = notes
    extraction.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return extraction


def reject(db: Session, extraction_id: str, notes: str | None = None) -> LLMExtraction:
    extraction = db.get(LLMExtraction, extraction_id)
    if extraction is None:
        raise ValueError(f"LLMExtraction {extraction_id} not found")
    extraction.review_status = "rejected"
    extraction.review_notes = notes
    extraction.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return extraction
