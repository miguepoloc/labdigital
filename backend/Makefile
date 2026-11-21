.PHONY: install hooks dev-up dev-down migrate migration test test-unit test-integration test-e2e lint format typecheck imports check run worker image

install:
	uv sync --all-extras

hooks:
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

dev-up:
	docker compose up -d
	@until docker compose exec -T postgres pg_isready -U labdigital > /dev/null 2>&1; do sleep 1; done

dev-down:
	docker compose down

migrate:
	uv run alembic upgrade head

migration:
	uv run alembic revision --autogenerate -m "$(m)"

run:
	uv run uvicorn backend.entrypoints.web.app:app --reload --port 18000

worker:
	uv run python -m backend.entrypoints.worker.main

image:
	docker build -t labdigital-api .

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

test-e2e:
	uv run pytest -m e2e

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

imports:
	uv run lint-imports

check: lint typecheck imports test
