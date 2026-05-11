"""
LLM-extraction review queue endpoints.

Pending-review records live in `llm_extractions` with review_status =
'pending_review'. This is the founder's main interactive surface — they
approve or reject low-confidence extractions before the data is treated
as canonical.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.api import schemas
from backend.api.deps import Pagination, pagination
from backend.db.connection import get_db
from backend.models import LLMExtraction

router = APIRouter(prefix="/llm-extractions", tags=["review"])


@router.get(
    "",
    response_model=schemas.Page[schemas.LLMExtractionWithRecord],
    summary="List LLM extractions (review queue)",
    description="Filter by status. Default ordering: lowest confidence first so the riskiest pending records surface first.",
)
def list_extractions(
    db: Session = Depends(get_db),
    page: Pagination = Depends(pagination),
    status: str = Query(
        "pending_review",
        description="auto_approved | pending_review | approved | rejected",
    ),
) -> schemas.Page[schemas.LLMExtractionWithRecord]:
    query = (
        select(LLMExtraction)
        .where(LLMExtraction.review_status == status)
        .options(joinedload(LLMExtraction.data_record))
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(LLMExtraction.confidence_score.asc())
        .limit(page.limit)
        .offset(page.offset)
    ).unique().all()

    return schemas.Page(
        items=[schemas.LLMExtractionWithRecord.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


def _apply_decision(
    db: Session,
    extraction_id: str,
    new_status: str,
    notes: str | None,
) -> LLMExtraction:
    try:
        pk = uuid.UUID(extraction_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"No extraction with id={extraction_id}") from None
    extraction = db.get(LLMExtraction, pk)
    if extraction is None:
        raise HTTPException(status_code=404, detail=f"No extraction with id={extraction_id}")
    if extraction.review_status not in {"pending_review", "auto_approved"}:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Extraction is already {extraction.review_status}; "
                "can only review pending_review or auto_approved rows."
            ),
        )
    extraction.review_status = new_status
    extraction.review_notes = notes
    extraction.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(extraction)
    return extraction


@router.post(
    "/{extraction_id}/approve",
    response_model=schemas.LLMExtraction,
    summary="Approve a pending extraction",
)
def approve_extraction(
    extraction_id: str,
    decision: schemas.ReviewDecision,
    db: Session = Depends(get_db),
) -> schemas.LLMExtraction:
    return schemas.LLMExtraction.model_validate(
        _apply_decision(db, extraction_id, "approved", decision.notes)
    )


@router.post(
    "/{extraction_id}/reject",
    response_model=schemas.LLMExtraction,
    summary="Reject a pending extraction",
)
def reject_extraction(
    extraction_id: str,
    decision: schemas.ReviewDecision,
    db: Session = Depends(get_db),
) -> schemas.LLMExtraction:
    return schemas.LLMExtraction.model_validate(
        _apply_decision(db, extraction_id, "rejected", decision.notes)
    )
