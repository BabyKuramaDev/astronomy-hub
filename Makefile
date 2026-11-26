.PHONY: install test lint format

install:
	uv sync
	uv run pre-commit install

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

format:
	uv run ruff format .
	uv run ruff check --fix .
