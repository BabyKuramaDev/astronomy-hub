---
name: hub-direction
description: Record the final decision of a star and package its dossier.
---

# hub-direction

## Commands

Run from `/workspace/astronomy-hub`; `bin/hub --help` lists every tool. Exact syntax, then an example:

```
bin/hub direction decide --tic <TIC> --mode {explore|eval} --reason <reason>
  e.g. bin/hub direction decide --tic 123456789 --mode eval --reason "vetting.json candidate, review.json reproduced"
bin/hub direction package-dossier --tic <TIC> [--dest <dest>]
  e.g. bin/hub direction package-dossier --tic 123456789
bin/setup-sandbox
  e.g. cd /workspace/astronomy-hub && bin/setup-sandbox
```

Do not explore the repository: these commands, the JSON they print and the dossier files are all you need.

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/setup-sandbox`: prepares the sandbox (creates a Python 3.12 environment from `uv.lock` when needed). Run it once at the start of the session, before any other tool.
- `bin/hub direction decide --tic <TIC> --mode <explore|eval> --reason "<why>"`: computes `final` by rule from `signal.json`, `catalog.json` (explore only), `vetting.json` and `review.json`, and writes `decision.json`. It reads only what the rule needs, in order. Exit 2 names the file still missing.
- `bin/hub direction package-dossier --tic <TIC>`: validates every dossier JSON against its contract and writes `/mnt/session/outputs/dossier-<TIC>.tar.gz`. Run it last.
