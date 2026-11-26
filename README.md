# Astronomy Hub

An open source hub of agents that searches public TESS light curves for
exoplanet transits and produces, for each star, a verifiable dossier with a
verdict and a report. It produces **candidates**, never confirmed planets.

The full design is in [`docs/SPEC.md`](docs/SPEC.md) (in Spanish).

## Status

M1 (signal tools) is done: the six signal tools run end to end on WASP-18 b
from MAST and recover its catalog period. Verification tools start in M2.

| Milestone | Scope |
| --- | --- |
| M0 Scaffold | Layout, `shared/contracts`, architecture tests, CI, secret scanning |
| **M1 Signal tools** | Download, clean, period search, fold, transit fit |
| M2 Verification tools | Crossmatch, vetting gates, independent reproduction, ephemeris, report |
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
make test-network  # end-to-end WASP-18 b run against MAST
make lint          # ruff + import-linter
make format        # ruff format + autofix
```

Run the signal chain for one star (dossier in `workspace/exoplanets/<tic>/`):

```sh
uv run python -m contexts.acquisition.cli fetch-lightcurves --tic <tic>
uv run python -m contexts.acquisition.cli fetch-star --tic <tic>
uv run python -m contexts.preparation.cli clean --tic <tic>
uv run python -m contexts.detection.cli search-period --tic <tic>
uv run python -m contexts.detection.cli fold --tic <tic> --peak p1
uv run python -m contexts.detection.cli select-peak --tic <tic> --peak p1 --reason "..."
uv run python -m contexts.modeling.cli fit-transit --tic <tic>
```

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
runtime/              adapter to Claude Managed Agents
tests/                shared and architecture tests
```

A context never imports another one. Contexts talk only through the dossier on
disk, whose JSON files are validated by the pydantic models in
`shared/contracts/`.

## License

[MIT](LICENSE). The vetting gates will be ported from
[open-exoplanet-hunt](https://github.com/Th0rgal/open-exoplanet-hunt) (MIT),
with attribution.
