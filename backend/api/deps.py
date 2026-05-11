"""Shared FastAPI dependencies — pagination, common query params."""

from dataclasses import dataclass

from fastapi import Query


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: int = Query(50, ge=1, le=500, description="Page size (1-500)."),
    offset: int = Query(0, ge=0, description="Rows to skip."),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)
