---
name: hub-acquisition
description: Download TESS SPOC light curves and TIC stellar parameters into the dossier. Use first, before any analysis of a star.
---

# hub-acquisition

## Commands

Run from `/workspace/astronomy-hub`; `bin/hub --help` lists every tool. Exact syntax, then an example:

```
bin/hub acquisition fetch-lightcurves --tic <TIC>
  e.g. bin/hub acquisition fetch-lightcurves --tic 123456789
bin/hub acquisition fetch-star --tic <TIC>
  e.g. bin/hub acquisition fetch-star --tic 123456789
```

Do not explore the repository: these commands, the JSON they print and the dossier files are all you need.

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub acquisition fetch-lightcurves --tic <TIC>`: picks sectors by the mission rule (`acquisition.sector_selection`), downloads the 2-minute SPOC files and writes one table per sector plus `lightcurve/manifest.json`. Takes about a minute. Transient MAST errors are retried; exit 3 means MAST is unavailable or the star has no 2-minute data. Report it, do not work around it.
- `bin/hub acquisition fetch-star --tic <TIC>`: writes `star.json` with stellar radius, mass, Teff and neighbors from the TIC. A parameter without an error in the TIC is null; that is expected.

## Reading the output

`sectors` lists the sectors used and `n_valid` the cadences kept per sector. A missing stellar radius makes the planet radius null later; it is not an error.
