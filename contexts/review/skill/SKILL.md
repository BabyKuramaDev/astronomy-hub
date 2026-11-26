---
name: hub-review
description: Reproduce the signal independently, then compare with the Searcher's result.
---

# hub-review

## Commands

Run from `/workspace/astronomy-hub`; `bin/hub --help` lists every tool. Exact syntax, then an example:

```
bin/hub review reproduce --tic <TIC>
  e.g. bin/hub review reproduce --tic 123456789
bin/hub review conclude --tic <TIC> --rationale <rationale>
  e.g. bin/hub review conclude --tic 123456789 --rationale "TLS finds the same period; depth ratio 1.1"
```

Do not explore the repository: these commands, the JSON they print and the dossier files are all you need.

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub review reproduce --tic <TIC>`: redoes cleaning (running median) and search (Transit Least Squares) from the raw per-sector tables. It never reads `signal.json`. Writes `review/reproduction.json` with the independent period, depth, duration and SDE; `detected` requires SDE at or above `review.sde_min`.
- `bin/hub review conclude --tic <TIC> --rationale "<why>"`: compares with `signal.json` by rule (period within `review.period_tolerance`, depth within `review.depth_tolerance`): reproduced, partial (other depth, or an integer alias of the period) or not_reproduced. It lists the disagreements. You only write the rationale.

## Rules

Run reproduce before reading `signal.json`, `model.json` or `vetting.json`. TLS measures depth at the bottom of the transit and BLS averages a box, so a TLS depth somewhat larger than the signal's is expected.
