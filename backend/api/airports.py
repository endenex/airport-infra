"""Airport list / detail endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api import schemas
from backend.api.deps import Pagination, pagination
from backend.db.connection import get_db
from backend.models import Airport as AirportModel
from backend.models import DataRecord

router = APIRouter(prefix="/airports", tags=["airports"])


@router.get(
    "",
    response_model=schemas.Page[schemas.Airport],
    summary="List airports",
    description="Paginated airport list with optional filters.",
)
def list_airports(
    db: Session = Depends(get_db),
    page: Pagination = Depends(pagination),
    country: str | None = Query(None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2"),
    tier: int | None = Query(None, ge=1, le=5),
    has_data: bool | None = Query(None, description="True → only airports with at least one data_record"),
) -> schemas.Page[schemas.Airport]:
    query = select(AirportModel)
    if country:
        query = query.where(AirportModel.country_code == country.upper())
    if tier is not None:
        query = query.where(AirportModel.tier == tier)
    if has_data is True:
        query = query.where(AirportModel.id.in_(select(DataRecord.airport_id).distinct()))
    elif has_data is False:
        query = query.where(~AirportModel.id.in_(select(DataRecord.airport_id).distinct()))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(AirportModel.iata_code.asc().nulls_last())
        .limit(page.limit)
        .offset(page.offset)
    ).all()

    return schemas.Page(
        items=[schemas.Airport.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{iata}",
    response_model=schemas.AirportSummary,
    summary="Airport detail with record-type roll-up",
)
def get_airport(iata: str, db: Session = Depends(get_db)) -> schemas.AirportSummary:
    airport = db.scalar(select(AirportModel).where(AirportModel.iata_code == iata.upper()))
    if airport is None:
        raise HTTPException(status_code=404, detail=f"No airport with IATA={iata}")

    type_counts: dict[str, int] = {
        row[0]: row[1]
        for row in db.execute(
            select(DataRecord.record_type, func.count())
            .where(DataRecord.airport_id == airport.id)
            .group_by(DataRecord.record_type)
        )
    }

    return schemas.AirportSummary(
        **schemas.Airport.model_validate(airport).model_dump(),
        records_total=sum(type_counts.values()),
        records_by_type=type_counts,
    )
