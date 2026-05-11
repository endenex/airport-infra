.PHONY: install dev-install migrate migrate-down test lint typecheck format check

install:
	uv sync

dev-install:
	uv sync --extra dev

migrate:
	uv run alembic upgrade head

migrate-down:
	uv run alembic downgrade -1

migrate-new:
	@read -p "Migration name: " name; uv run alembic revision --autogenerate -m "$$name"

test:
	uv run pytest -v

test-cov:
	uv run pytest --cov=backend --cov=ingestion --cov=llm_pipelines --cov-report=term-missing

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy backend/ ingestion/ llm_pipelines/

check: lint typecheck test

run-api:
	uv run uvicorn backend.main:app --reload --port 8000
