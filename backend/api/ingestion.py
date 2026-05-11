"""Ingestion run audit endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api import schemas
from backend.api.deps import Pagination, pagination
from backend.db.connection import get_db
from backend.models import IngestionRun

router = APIRouter(prefix="/ingestion-runs", tags=["ingestion"])


@router.get(
    "",
    response_model=schemas.Page[schemas.IngestionRun],
    summary="List ingestion runs (newest first)",
    description="Operational view of ingestor executions. Filter by source_id or status.",
)
def list_ingestion_runs(
    db: Session = Depends(get_db),
    page: Pagination = Depends(pagination),
    source_id: str | None = Query(None, description="Filter to one source (e.g. 'esma_xbrl')."),
    status: str | None = Query(None, description="Filter by status: running | completed | failed."),
) -> schemas.Page[schemas.IngestionRun]:
    query = select(IngestionRun)
    if source_id:
        query = query.where(IngestionRun.source_id == source_id)
    if status:
        query = query.where(IngestionRun.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(IngestionRun.started_at.desc()).limit(page.limit).offset(page.offset)
    ).all()

    return schemas.Page(
        items=[schemas.IngestionRun.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
