---
name: hub-vetting
description: Try to reject a signal with the ten vetting gates, rerun doubtful gates, and record the verdict.
---

# hub-vetting

## Commands

Run from `/workspace/astronomy-hub`; `bin/hub --help` lists every tool. Exact syntax, then an example:

```
bin/hub vetting run-gates --tic <TIC>
  e.g. bin/hub vetting run-gates --tic 123456789
bin/hub vetting run-gate --tic <TIC> --gate <gate> [--duration-scale <duration_scale>] [--window-durations <window_durations>]
  e.g. bin/hub vetting run-gate --tic 123456789 --gate odd-even --duration-scale 0.8
bin/hub vetting conclude --tic <TIC> --rationale <rationale>
  e.g. bin/hub vetting conclude --tic 123456789 --rationale "odd-even: 0.4 sigma; secondary: none; all gates pass"
```

Do not explore the repository: these commands, the JSON they print and the dossier files are all you need.

Run every tool from the repository as `bin/hub <context> <tool> --tic <TIC> [options]` (the repository is mounted at `/workspace/astronomy-hub`; run `cd /workspace/astronomy-hub` first). Each tool prints a short JSON summary on stdout and writes its files into the dossier `workspace/exoplanets/<TIC>/`. Exit codes: 0 ok, 2 invalid input, 3 data not available; the error is one line on stderr. Thresholds live in `missions/exoplanets/mission.yaml`; read them there, never assume them.

## Tools

- `bin/hub vetting run-gates --tic <TIC>`: runs the ten gates once and prints, per gate, status, severity, value, threshold and a note, plus `verdict_if_concluded`.
- `bin/hub vetting run-gate --tic <TIC> --gate <id> [--duration-scale X] [--window-durations Y]`: reruns one gate with other measurement parameters (within the ranges in `vetting.measurement`); thresholds never change. Gates `catalog`, `coverage`, `snr` and `plausibility` cannot be rerun.
- `bin/hub vetting conclude --tic <TIC> --rationale "<one sentence per gate that matters>"`: combines the runs of every gate (all pass: pass; all fail: fail; any mixture: marginal) and computes the verdict by rule: a hard fail is false_positive, a soft fail or any marginal is inconclusive, all passing is candidate. You only write the rationale.
- `bin/hub detection fold --tic <TIC> --period <P> --epoch <T0> --duration <hours>` helps you look at a doubtful case.

## Gates

`catalog` (info, never counts), `coverage`, `snr`, `holdout`, `odd-even`, `secondary`, `plausibility`, `centroid`, `coherence`, `rotation`. Severities and thresholds are in `vetting.gates` of the mission file. A significant secondary eclipse shallower than the mission's ratio passes: it is the occultation of a planet.
