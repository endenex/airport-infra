"""Data record list / detail endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api import schemas
from backend.api.deps import Pagination, pagination
from backend.db.connection import get_db
from backend.models import Airport, DataRecord

router = APIRouter(prefix="/records", tags=["records"])


@router.get(
    "",
    response_model=schemas.Page[schemas.DataRecord],
    summary="List data records",
    description="Paginated records list with filters by airport / source / type / period.",
)
def list_records(
    db: Session = Depends(get_db),
    page: Pagination = Depends(pagination),
    iata: str | None = Query(None, description="Filter by airport IATA code."),
    source_id: str | None = Query(None, description="Filter by source_id (e.g. 'esma_xbrl')."),
    record_type: str | None = Query(
        None,
        description="Filter by record_type (FINANCIAL, OPERATIONAL, CLIMATE, OWNERSHIP, ...).",
    ),
    period_start_gte: date | None = Query(None, description="period_start >= this date."),
    period_end_lte: date | None = Query(None, description="period_end <= this date."),
) -> schemas.Page[schemas.DataRecord]:
    query = select(DataRecord)

    if iata:
        airport = db.scalar(select(Airport).where(Airport.iata_code == iata.upper()))
        if airport is None:
            # Treat unknown IATA as zero results rather than 404 — list endpoints
            # should be tolerant.
            return schemas.Page(items=[], total=0, limit=page.limit, offset=page.offset)
        query = query.where(DataRecord.airport_id == airport.id)
    if source_id:
        query = query.where(DataRecord.source_id == source_id)
    if record_type:
        query = query.where(DataRecord.record_type == record_type.upper())
    if period_start_gte:
        query = query.where(DataRecord.period_start >= period_start_gte)
    if period_end_lte:
        query = query.where(DataRecord.period_end <= period_end_lte)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(DataRecord.period_end.desc().nulls_last(), DataRecord.created_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()

    return schemas.Page(
        items=[schemas.DataRecord.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{record_id}",
    response_model=schemas.DataRecord,
    summary="Get a single data record by ID",
)
def get_record(record_id: str, db: Session = Depends(get_db)) -> schemas.DataRecord:
    record = db.get(DataRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No record with id={record_id}")
    return schemas.DataRecord.model_validate(record)
