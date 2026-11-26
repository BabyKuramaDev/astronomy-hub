---
name: hub-detection
description: Find periodic transit-like dips with BLS, inspect them by folding, and record the chosen peak or no signal.
---

# hub-detection

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub detection search-period --tic <TIC>`: BLS over the clean curve. `peaks` lists the best distinct peaks (id, period, duration, depth, SNR, SDE, transits); `discarded` lists harmonics and non-positive depths. `inverted_snr_max` is the noise floor: the best SNR of the same search on the inverted curve, where every dip is noise.
- `bin/hub detection fold --tic <TIC> --peak <id>` (or `--period --epoch --duration`): folds the curve and prints depth, out-of-transit scatter, odd/even depths with their significance and a binned profile. It writes `folds/<tag>.json` and a figure.
- `bin/hub detection select-peak --tic <TIC> --peak <id> --reason "<why>"` or `--no-signal --reason "<why>"`: records the decision in `signal.json`. It refuses a peak below `detection.snr_min` or `detection.min_transits` (exit 2): pick another peak or record no signal.

## How to judge peaks

- A peak whose SNR is not above `inverted_snr_max` is indistinguishable from noise.
- Prefer the peak with the clean, box- or U-shaped fold and consistent odd/even depths. A V shape, very different odd/even depths, or a dip carried by one sector are warning signs, but vetting tests them formally: note them in `--reason`, do not over-filter.
- Periods that are integer ratios of a better peak are already discarded as harmonics.
- Recording no signal is a correct and common outcome.
