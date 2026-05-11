"""Transactions endpoints — closed deals and counterfactuals (Layer γ)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api import schemas
from backend.api.deps import Pagination, pagination
from backend.db.connection import get_db
from backend.models import Airport, MethodologyVersion
from backend.models.transaction import (
    VALID_FAILURE_STATUS,
    VALID_PRICE_CONFIDENCE,
    VALID_STATES,
    VALID_TRANSACTION_TYPES,
)
from backend.models.transaction import (
    Transaction as TxnModel,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get(
    "",
    response_model=schemas.Page[schemas.Transaction],
    summary="List transactions (closed + counterfactual)",
    description=(
        "Paginated transaction list with filters. State filter is essential "
        "for Layer γ analysis — e.g. state=abandoned to see deals that died."
    ),
)
def list_transactions(
    db: Session = Depends(get_db),
    page: Pagination = Depends(pagination),
    iata: str | None = Query(None, description="Filter by airport IATA code."),
    state: str | None = Query(
        None,
        description="closed | abandoned | pulled | bid_lost | postponed | rumored",
    ),
    transaction_type: str | None = Query(
        None,
        description="acquisition | divestment | refinancing | ipo | etc.",
    ),
    year: int | None = Query(None, description="Filter by year of announce_date or close_date."),
) -> schemas.Page[schemas.Transaction]:
    query = select(TxnModel)

    if iata:
        airport = db.scalar(select(Airport).where(Airport.iata_code == iata.upper()))
        if airport is None:
            # List endpoint: unknown IATA → empty results (don't 404)
            return schemas.Page(items=[], total=0, limit=page.limit, offset=page.offset)
        query = query.where(TxnModel.airport_id == airport.id)
    if state:
        query = query.where(TxnModel.state == state)
    if transaction_type:
        query = query.where(TxnModel.transaction_type == transaction_type)
    if year:
        # Match either announce or close in this year — captures both
        # forward-looking and retrospective queries.
        query = query.where(
            (func.extract("year", TxnModel.announce_date) == year)
            | (func.extract("year", TxnModel.close_date) == year)
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(
            TxnModel.close_date.desc().nulls_last(),
            TxnModel.announce_date.desc().nulls_last(),
        )
        .limit(page.limit)
        .offset(page.offset)
    ).all()

    return schemas.Page(
        items=[schemas.Transaction.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{transaction_id}",
    response_model=schemas.Transaction,
    summary="Get a single transaction by ID",
)
def get_transaction(transaction_id: str, db: Session = Depends(get_db)) -> schemas.Transaction:
    try:
        pk = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"No transaction with id={transaction_id}") from None
    txn = db.get(TxnModel, pk)
    if txn is None:
        raise HTTPException(status_code=404, detail=f"No transaction with id={transaction_id}")
    return schemas.Transaction.model_validate(txn)


@router.post(
    "",
    response_model=schemas.Transaction,
    status_code=201,
    summary="Create a transaction (manual entry)",
    description=(
        "Manual transaction entry. Used for seeding initial data before the "
        "LLM-from-press-release ingestor lands. Validates state, "
        "transaction_type, price_information_confidence, and "
        "reason_for_failure_status against the allowed lexicon."
    ),
)
def create_transaction(
    body: schemas.TransactionCreate, db: Session = Depends(get_db)
) -> schemas.Transaction:
    if body.state not in VALID_STATES:
        raise HTTPException(
            status_code=422,
            detail=f"state must be one of {sorted(VALID_STATES)}; got {body.state!r}",
        )
    if body.transaction_type not in VALID_TRANSACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"transaction_type must be one of {sorted(VALID_TRANSACTION_TYPES)}; got {body.transaction_type!r}",
        )
    if (body.price_information_confidence is not None
            and body.price_information_confidence not in VALID_PRICE_CONFIDENCE):
        raise HTTPException(
            status_code=422,
            detail=f"price_information_confidence must be one of {sorted(VALID_PRICE_CONFIDENCE)}",
        )
    if (body.reason_for_failure_status is not None
            and body.reason_for_failure_status not in VALID_FAILURE_STATUS):
        raise HTTPException(
            status_code=422,
            detail=f"reason_for_failure_status must be one of {sorted(VALID_FAILURE_STATUS)}",
        )

    # Methodology version: the most recent baseline (1.0.0 unless overridden).
    mv = db.scalar(
        select(MethodologyVersion).order_by(MethodologyVersion.effective_from.asc())
    )
    if mv is None:
        raise HTTPException(status_code=500, detail="No methodology version configured")

    txn = TxnModel(
        airport_id=body.airport_id,
        asset_name=body.asset_name,
        announce_date=body.announce_date,
        signing_date=body.signing_date,
        close_date=body.close_date,
        state=body.state,
        transaction_type=body.transaction_type,
        enterprise_value=body.enterprise_value,
        equity_value=body.equity_value,
        currency=body.currency,
        stake_percent=body.stake_percent,
        price_information_confidence=body.price_information_confidence,
        reason_for_failure_status=body.reason_for_failure_status,
        reason_for_failure_text=body.reason_for_failure_text,
        buyer_entities=[p.model_dump() for p in body.buyer_entities] or None,
        seller_entities=[p.model_dump() for p in body.seller_entities] or None,
        rival_bids=[p.model_dump() for p in body.rival_bids] or None,
        source_url=body.source_url,
        source_document_id=body.source_document_id,
        retrieved_at=datetime.now(timezone.utc),
        methodology_version_id=mv.id,
        notes=body.notes,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return schemas.Transaction.model_validate(txn)
