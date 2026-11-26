---
name: hub-modeling
description: Fit a transit model to the selected signal. Use after select-peak.
---

# hub-modeling

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub modeling fit-transit --tic <TIC>`: quick fit (least squares with a jitter term, about a second). Writes `model.json` with Rp/R*, impact parameter, a/R*, period, epoch, T14, jitter and the planet radius when the TIC gives the stellar radius.
- `bin/hub modeling fit-transit --tic <TIC> --mode mcmc`: emcee posterior, several minutes. It only runs when `vetting.json` says candidate for the current signal, and only in explore mode: never run it in eval mode.

## Reading the output

`warnings` explains a null planet radius or an unconverged chain. A planet radius far above Jupiter's is a vetting concern, not a reason to stop.
