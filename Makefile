.PHONY: install test test-network test-platform lint format dossier hello probe

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

# Managed Agents (spends API credits; budget per session and a total cap in runtime/).
hello:
	uv run python -m runtime.hello --mode $(MODE)

probe:
	uv run python -m runtime.probe

test-platform:
	uv run pytest -m platform
