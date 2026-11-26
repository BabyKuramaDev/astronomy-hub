---
name: hub-followup
description: Predict the next transits of a fitted signal.
---

# hub-followup

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub followup ephemeris --tic <TIC>`: reads `model.json` and lists the transits of the next `followup.horizon_days` from today (UTC), with ingress, egress and a 1-sigma timing error. Writes `ephemeris.json`. Times are barycentric shown in UTC.
