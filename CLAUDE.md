# CLAUDE.md

Astronomy Hub: agents that search TESS light curves for exoplanet transits.
`docs/SPEC.md` is the source of truth (in Spanish). Read it before changing
behavior, and update it in the same change when a decision changes.

## Commands

- `make install`: `uv sync` and pre-commit hooks (needs `gitleaks` on PATH)
- `make test`: pytest, including the architecture tests
- `make lint`: `ruff check`, `ruff format --check`, `lint-imports`
- `make format`: format and autofix
- Run a tool: `uv run python -m contexts.<context>.cli <tool> --tic <id> --workspace <dir>`

## Working rules

- Milestones go in order (M0 to M5). Do not start the next one until the
  current one meets its acceptance criterion in the spec.
- Small commits with messages in English. Never push unless asked.
- Never commit `.env` or any key. `.env.example` lists the variables.
- No API credits are used before M3.

## Architecture (enforced in CI)

- A context never imports another context; it depends only on `shared/`.
  Contexts talk only through the dossier (`workspace/<mission>/<tic_id>/`).
- Layers inside a context: `cli -> infrastructure -> application -> domain`.
  A layer may import the ones to its right, never to its left.
- `domain/` and `shared/kernel/` do no I/O: no `os`, `pathlib`, `sys`,
  network or file libraries, no `open`, `input` or `print`.
  See `tests/architecture/domain_purity.py`.
- `shared/` and `evals/` never import `contexts/`.
- Only `runtime/` imports `anthropic`.
- Mission-specific values come from `missions/<mission>/mission.yaml`, never
  hardcoded in a context.

import-linter contracts live in `pyproject.toml`; each one has a test that
injects a violation into a temporary copy of the repo.

## Contracts

- Every dossier JSON is an `Envelope[DataT]` from `shared/contracts/`.
  Models are frozen, reject unknown fields, NaN and infinities.
- `created_at` must be UTC. `inputs` maps dossier-relative paths to
  `sha256:<hex>`.
- The output hash logged in `log.jsonl` is `data_sha256(envelope)`, computed
  over `data` only.
- Tools validate when writing; evals validate when reading. Agents never edit
  another context's JSON by hand.

## Tools

- `cli.py` only parses arguments and calls the use case's `execute()`.
- Read and write only inside the dossier; print a short JSON summary on stdout.
- Exit codes: 0 ok, 2 invalid input, 3 data not available. Errors go to
  stderr on one line.
- Deterministic and idempotent, fixed seeds. Tests run without LLM or network.

## Open questions

Tracked at the end of `docs/SPEC.md`. Still open for M1/M2: which tool each
agent uses to record its decision (chosen peak, verdicts, `decision.json`).
