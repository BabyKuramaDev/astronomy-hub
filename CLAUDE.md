# CLAUDE.md

Astronomy Hub: agents that search TESS light curves for exoplanet transits.
`docs/SPEC.md` is the source of truth (in Spanish). Read it before changing
behavior, and update it in the same change when a decision changes.

## Commands

- `make install`: `uv sync` and pre-commit hooks (needs `gitleaks` on PATH)
- `make test`: pytest without network, including the architecture tests
- `make test-network`: tests marked `network` (WASP-18 b against MAST); not in CI
- `uv run python -m tests.fixtures.wasp18.build`: rebuild the WASP-18 b fixtures (network)
- `make lint`: `ruff check`, `ruff format --check`, `lint-imports`
- `make format`: format and autofix
- Run a tool: `uv run python -m contexts.<context>.cli <tool> --tic <id> --workspace <dir>`

## Working rules

- Milestones go in order (M0 to M5). Do not start the next one until the
  current one meets its acceptance criterion in the spec, and never start one
  without being asked. At the end of a milestone, report and stop.
- Plan before code: for each milestone, first check free disk space (stop and
  warn if under 5 GB), then propose the plan (files, new dependencies with their
  approximate size, open questions) and wait for the author's ok.
- Fold the author's answers into `docs/SPEC.md` before or with the code, so spec
  and code match. Questions outside the current milestone go to the spec's open
  questions instead of being resolved early.
- Small commits with messages in English. Never push unless asked.
- New dependencies: only what the milestone needs, pinned with `==`.
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
- Shared tool plumbing lives in `shared/toolkit` (`ToolCli`, `Dossier`, `ToolMeta`):
  every tool validates its contract on write and appends a `log.jsonl` entry.
- Thresholds and parameters come from `missions/<mission>/mission.yaml`, validated
  by `shared/mission.py`. Add new ones there, never as constants in a context.
- Downloads go to the dossier; astropy/astroquery caches go to `<dossier>/.cache`,
  matplotlib's font cache to `<workspace>/.cache`. Never write to global caches.

## Tests

- `make test` must stay offline: the root `conftest.py` blocks network access for
  tests without the `network` marker. Tests that hit MAST get `@pytest.mark.network`.
- Fixtures stay under 1 MB with their provenance written next to them. Astronomical
  reference values come from a catalog query (see `tests/fixtures/wasp18/`), never
  from memory.

## Open questions

Tracked at the end of `docs/SPEC.md`. Detection records its choice with
`select-peak`; still open for M2: how Vetting, Review and the Director record theirs.

## Environment notes

- batman 2.5.3 imports `distutils`. The pinned `setuptools` dependency provides it
  through `distutils-precedence.pth`; if batman fails with `No module named
  'distutils'`, check that the `.pth` files in `.venv` are not flagged hidden
  (`ls -lO`).
- Keep the checkout outside iCloud-managed folders such as `~/Documents`: the file
  provider marks dotfiles hidden (Python then skips `.pth` files in `.venv`) and
  creates `"<name> 2"` conflict copies. Check disk space before large downloads.
