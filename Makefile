.PHONY: install test test-network test-platform lint format dossier hello probe eval-set eval-baseline eval-pilot eval-dev eval-holdout

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

# Evals: labels and per-star results live in ~/Code/astronomy-hub-evals (HUB_EVALS_DIR).
eval-set:
	uv run python -m evals.build_set --from-snapshot

eval-baseline:
	uv run python -m evals.baseline
	uv run python -m evals.scorer baseline

eval-pilot:
	uv run python -m runtime.eval_agents --pilot --cap-cents 1000
	uv run python -m evals.scorer agents --compare

# The development set has its own cap, set after the pilot: make eval-dev CAP=<cents>
eval-dev:
	@test -n "$(CAP)" || (echo "make eval-dev needs CAP=<cents>, its own spend cap" >&2; exit 2)
	uv run python -m runtime.eval_agents --split dev --milestone M4-dev --cap-cents $(CAP)
	uv run python -m evals.scorer agents --compare

# The holdout: run once, at the end; only aggregated tables are printed (no star is shown).
eval-holdout:
	@test -n "$(CAP)" || (echo "make eval-holdout needs CAP=<cents>, its own spend cap" >&2; exit 2)
	uv run python -m evals.baseline --set v0.1 --splits holdout --quiet
	uv run python -m evals.scorer baseline --splits holdout --aggregate-only
	uv run python -m runtime.eval_agents --split holdout --milestone M4-holdout --cap-cents $(CAP) --quiet
	uv run python -m evals.scorer agents --splits holdout --aggregate-only
