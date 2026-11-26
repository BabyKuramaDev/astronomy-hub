---
name: hub-catalog
description: Establish whether the star or the signal is already catalogued, and record literature sources.
---

# hub-catalog

## Commands

Run from `/workspace/astronomy-hub`; `bin/hub --help` lists every tool. Exact syntax, then an example:

```
bin/hub catalog crossmatch --tic <TIC>
  e.g. bin/hub catalog crossmatch --tic 123456789
bin/hub catalog add-literature --tic <TIC> --title <title> --url <url> [--note <note>]
  e.g. bin/hub catalog add-literature --tic 123456789 --title "Discovery paper" --url https://arxiv.org/abs/2401.00001 --note "Reports the 3.2 d period"
```

Do not explore the repository: these commands, the JSON they print and the dossier files are all you need.

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub catalog crossmatch --tic <TIC>`: looks the TIC up in the NASA Exoplanet Archive (confirmed planets and the TOI list) and in the ExoFOP CTOIs, and marks which entries match the period in `signal.json` (within 1 percent or an integer ratio). `status` only counts entries at the signal's period; other periods become `notes`. Writes `catalog.json`.
- `bin/hub catalog add-literature --tic <TIC> --title "<title>" --url <url> --note "<what it says>"`: adds one source to `catalog.json`. Use it for every relevant paper or page you find; a URL already recorded is skipped.

## Rules

- Your web tools reach a few catalog and literature sites (the NASA Exoplanet Archive, ExoFOP, arXiv, ADS). Record every source you use with its URL.
- Do not judge whether the signal is real, only whether it is known.
