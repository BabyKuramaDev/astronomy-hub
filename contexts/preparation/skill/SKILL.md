---
name: hub-preparation
description: Clean and detrend the downloaded light curve. Use after fetch-lightcurves and before search-period.
---

# hub-preparation

## Commands

Run from `/workspace/astronomy-hub`; `bin/hub --help` lists every tool. Exact syntax, then an example:

```
bin/hub preparation clean --tic <TIC>
  e.g. bin/hub preparation clean --tic 123456789
```

Do not explore the repository: these commands, the JSON they print and the dossier files are all you need.

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub preparation clean --tic <TIC>`: normalizes each sector, removes the trend (biweight), clips upward outliers only (never dips) and stitches the sectors into `lightcurve_clean.parquet`.

## Reading the output

`rms_ppm` is the scatter of the clean curve; `clipped` counts removed points per sector. A very high `rms_ppm` means shallow transits will be hard to find.
