---
name: hub-followup
description: Predict the next transits of a fitted signal.
---

# hub-followup

## Commands

Run from `/workspace/astronomy-hub`; `bin/hub --help` lists every tool. Exact syntax, then an example:

```
bin/hub followup ephemeris --tic <TIC> [--start <start>]
  e.g. bin/hub followup ephemeris --tic 123456789
```

Do not explore the repository: these commands, the JSON they print and the dossier files are all you need.

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub followup ephemeris --tic <TIC>`: reads `model.json` and lists the transits of the next `followup.horizon_days` from today (UTC), with ingress, egress and a 1-sigma timing error. Writes `ephemeris.json`. Times are barycentric shown in UTC.
