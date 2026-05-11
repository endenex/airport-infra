"""Cross-validation list endpoint — surfaces triangulation results."""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.api import schemas
from backend.api.deps import Pagination, pagination
from backend.db.connection import get_db
from backend.models import CrossValidation

router = APIRouter(prefix="/cross-validations", tags=["validation"])


class CrossValidationOut(BaseModel):
    """Cross-validation row with the two records it compares embedded."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    primary_record_id: str
    comparison_record_id: str
    field_name: str
    primary_value: dict[str, Any] | None
    comparison_value: dict[str, Any] | None
    agreement: bool
    discrepancy_pct: float | None
    flagged_for_review: bool
    created_at: datetime
    # Hydrated for convenience — period and airport_id come from either
    # side (they match by construction).
    period_end: date | None = None
    airport_id: uuid.UUID | None = None


@router.get(
    "",
    response_model=schemas.Page[CrossValidationOut],
    summary="List cross-validations",
    description=(
        "Pairwise cross-source comparisons. Filter by field_name (the concept, "
        "e.g. passengers_total), agreement state, or flagged_for_review."
    ),
)
def list_validations(
    db: Session = Depends(get_db),
    page: Pagination = Depends(pagination),
    field_name: str | None = Query(None, description="Filter by concept (e.g. passengers_total)."),
    agreement: bool | None = Query(None, description="True = within threshold, False = disagreement."),
    flagged: bool | None = Query(None, alias="flagged_for_review",
                                  description="Only rows flagged for human review."),
) -> schemas.Page[CrossValidationOut]:
    query = select(CrossValidation).options(joinedload(CrossValidation.primary_record))
    if field_name:
        query = query.where(CrossValidation.field_name == field_name)
    if agreement is not None:
        query = query.where(CrossValidation.agreement == agreement)
    if flagged is not None:
        query = query.where(CrossValidation.flagged_for_review == flagged)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        # Order: flagged first, then by absolute discrepancy — riskiest at the top
        query.order_by(
            CrossValidation.flagged_for_review.desc(),
            func.abs(CrossValidation.discrepancy_pct).desc().nulls_last(),
        )
        .limit(page.limit)
        .offset(page.offset)
    ).unique().all()

    items = []
    for r in rows:
        primary = r.primary_record
        items.append(CrossValidationOut(
            id=r.id,
            primary_record_id=r.primary_record_id,
            comparison_record_id=r.comparison_record_id,
            field_name=r.field_name,
            primary_value=r.primary_value,
            comparison_value=r.comparison_value,
            agreement=r.agreement,
            discrepancy_pct=r.discrepancy_pct,
            flagged_for_review=r.flagged_for_review,
            created_at=r.created_at,
            period_end=primary.period_end if primary else None,
            airport_id=primary.airport_id if primary else None,
        ))
    return schemas.Page(items=items, total=total, limit=page.limit, offset=page.offset)
