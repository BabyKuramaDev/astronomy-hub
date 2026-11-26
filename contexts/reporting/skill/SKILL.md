---
name: hub-reporting
description: Write the human-readable report of the dossier.
---

# hub-reporting

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub reporting render-report --tic <TIC> [--summary "<your prose>"]`: renders `report.md` from the dossier with a fixed template: verdict first, every number with the file it came from, limitations and provenance. It needs `decision.json`. Files computed on another `signal.json` are left out and named.

## Writing the summary

Two to five sentences: the verdict, the key numbers with their files, and what observation would confirm or refute it. Write candidate, never planet or discovery.
