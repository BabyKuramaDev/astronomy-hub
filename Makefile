.PHONY: install test test-network lint format dossier

MODE ?= eval

install:
	uv sync --all-groups
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

# Complete dossier without an LLM (network). TIC defaults to WASP-18 b's, from the fixtures.
dossier:
	@uv run python -m scripts.build_dossier --mode $(MODE) $(if $(TIC),--tic $(TIC),)
