# Astronomy Hub

An open source hub of agents that searches public TESS light curves for
exoplanet transits and produces, for each star, a verifiable dossier with a
verdict and a report. It produces **candidates**, never confirmed planets.

The full design is in [`docs/SPEC.md`](docs/SPEC.md) (in Spanish).

## Status

M2 (verification tools) is done: a script builds WASP-18 b's complete dossier
without an LLM, through the ten vetting gates and an independent reproduction, and
in blind (eval) mode it ends in `candidate`. Synthetic eclipsing binaries, glitches,
rotators and inverted light curves are rejected. Agents start in M3.

| Milestone | Scope |
| --- | --- |
| M0 Scaffold | Layout, `shared/contracts`, architecture tests, CI, secret scanning |
| M1 Signal tools | Download, clean, period search, fold, transit fit |
| **M2 Verification tools** | Crossmatch, vetting gates, independent reproduction, ephemeris, report |
| M3 Agent skeleton | Six agents on Claude Managed Agents, with a budget per session |
| M4 Evals | Eval set, runner and scorer in blind mode |
| M5 Iteration | Prompt and skill tuning against the dev set |

## Requirements

- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 if needed)
- [gitleaks](https://github.com/gitleaks/gitleaks) on `PATH` for the pre-commit hook (`brew install gitleaks`)

## Usage

```sh
make install   # uv sync + pre-commit hooks
make test          # pytest without network, including the architecture tests
make test-network  # end-to-end WASP-18 b run against MAST and the catalogs
make dossier       # WASP-18 b's complete dossier without an LLM (TIC=<id> MODE=explore|eval)
make hello         # the same star on Claude Managed Agents, six agents (spends API credits)
make lint          # ruff + import-linter
make format        # ruff format + autofix
```

Or run the tools one by one, as the agents will (dossier in `workspace/exoplanets/<tic>/`):

```sh
uv run python -m contexts.acquisition.cli fetch-lightcurves --tic <tic>
uv run python -m contexts.acquisition.cli fetch-star --tic <tic>
uv run python -m contexts.preparation.cli clean --tic <tic>
uv run python -m contexts.detection.cli search-period --tic <tic>
uv run python -m contexts.detection.cli fold --tic <tic> --peak p1
uv run python -m contexts.detection.cli select-peak --tic <tic> --peak p1 --reason "..."
uv run python -m contexts.modeling.cli fit-transit --tic <tic>             # quick
uv run python -m contexts.catalog.cli crossmatch --tic <tic>
uv run python -m contexts.vetting.cli run-gates --tic <tic>
uv run python -m contexts.vetting.cli run-gate --tic <tic> --gate odd-even --duration-scale 0.8
uv run python -m contexts.vetting.cli conclude --tic <tic> --rationale "..."
uv run python -m contexts.modeling.cli fit-transit --tic <tic> --mode mcmc # candidates only
uv run python -m contexts.review.cli reproduce --tic <tic>
uv run python -m contexts.review.cli conclude --tic <tic> --rationale "..."
uv run python -m contexts.direction.cli decide --tic <tic> --mode explore --reason "..."
uv run python -m contexts.followup.cli ephemeris --tic <tic>
uv run python -m contexts.reporting.cli render-report --tic <tic>
```

Verdicts come from fixed rules in the tools; an agent only gives the rationale.

## Layout

```
contexts/<context>/   one bounded context per astronomer role (10)
  domain/             pure model, no I/O
  application/        use cases, one execute() each
  infrastructure/     repositories and adapters
  cli.py              exposes each use case as a tool
  tests/
shared/               kernel value objects, dossier contracts, common prompts
missions/exoplanets/  mission.yaml
evals/                eval set, runner and scorer (reads the dossier only)
runtime/              adapter to Claude Managed Agents: sessions, events, cost, audit
bin/                  hub (run a tool in the sandbox) and setup-sandbox
scripts/              build_dossier.py: the whole pipeline without an LLM
tests/                shared, architecture and end-to-end tests, WASP-18 b fixtures
```

A context never imports another one. Contexts talk only through the dossier on
disk, whose JSON files are validated by the pydantic models in
`shared/contracts/`.

## License

[MIT](LICENSE). The vetting gates and their synthetic controls are ported from
[open-exoplanet-hunt](https://github.com/Th0rgal/open-exoplanet-hunt) (MIT); their
license notice is in
[`contexts/vetting/THIRD_PARTY_NOTICE.md`](contexts/vetting/THIRD_PARTY_NOTICE.md).
