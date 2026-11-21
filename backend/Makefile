.PHONY: install hooks dev-up dev-down migrate migration test test-unit lint format typecheck imports check

install:
	uv sync --all-extras

hooks:
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

dev-up:
	docker compose up -d
	@echo "Waiting for Postgres..."
	@until docker compose exec -T postgres pg_isready -U backend > /dev/null 2>&1; do sleep 1; done

dev-down:
	docker compose down

migrate:
	uv run alembic upgrade head

migration:
	uv run alembic revision --autogenerate -m "$(m)"

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

imports:
	uv run lint-imports

check: lint typecheck imports test-unit
