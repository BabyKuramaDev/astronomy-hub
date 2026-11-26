.PHONY: install test test-network lint format

install:
	uv sync
	uv run pre-commit install

test:
	uv run pytest

test-network:
	uv run pytest -m network

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

format:
	uv run ruff format .
	uv run ruff check --fix .
