# Phase A: 3-review

- code: `913ffa01690ea5f2` (before: `6785b95650ce56f7`)
- stars: 180 (calib and dev; the holdout is not read)

## Verdict

- final recall on planets: 0.264 -> 0.319 (19 -> 23 of 72)
- new accepted false positives: 0
- new grave errors: 0
- **accepted** by the rule

## Before

Planets, calib and dev pooled: final recall 0.264 (19 of 72); accepted false positives 3; grave errors 11 (5 on the catalog period, the rest on another signal).

| split | group | n | detection recall | final recall | candidate, wrong period | FP rejected | FP accepted | no_signal | false alarm | inconclusive | reproduced | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calib | planet_deep | 30 | 0.77 | 0.27 | 0 | - | - | - | - | 0.43 | 0.43 | 0 |
| calib | planet_small | 30 | 0.77 | 0.23 | 0 | - | - | - | - | 0.47 | 0.60 | 0 |
| calib | false_positive | 60 | - | - | - | 0.52 | 0.05 | - | - | 0.33 | 0.25 | 0 |
| calib | no_signal | 30 | - | - | - | - | - | 0.47 | 0.00 | 0.33 | 0.03 | 0 |
| dev | planet_deep | 6 | 1.00 | 0.33 | 0 | - | - | - | - | 0.67 | 0.50 | 0 |
| dev | planet_small | 6 | 0.50 | 0.33 | 0 | - | - | - | - | 0.17 | 0.50 | 0 |
| dev | false_positive | 12 | - | - | - | 0.50 | 0.00 | - | - | 0.42 | 0.25 | 0 |
| dev | no_signal | 6 | - | - | - | - | - | 0.50 | 0.00 | 0.33 | 0.00 | 0 |

False positives:

| split | n | rejected, catalog period | rejected, other period | not detected | inconclusive | accepted |
|---|---|---|---|---|---|---|
| calib | 60 | 25 | 6 | 6 | 20 | 3 |
| dev | 12 | 5 | 1 | 1 | 5 | 0 |

Fits:

| split | group | n | failed fits | incomplete |
|---|---|---|---|---|
| calib | planet_deep | 30 | 0 | 0 |
| calib | planet_small | 30 | 0 | 0 |
| calib | false_positive | 60 | 2 | 0 |
| calib | no_signal | 30 | 1 | 0 |
| dev | planet_deep | 6 | 0 | 0 |
| dev | planet_small | 6 | 0 | 0 |
| dev | false_positive | 12 | 1 | 0 |
| dev | no_signal | 6 | 1 | 0 |

## After

Planets, calib and dev pooled: final recall 0.319 (23 of 72); accepted false positives 3; grave errors 11 (5 on the catalog period, the rest on another signal).

| split | group | n | detection recall | final recall | candidate, wrong period | FP rejected | FP accepted | no_signal | false alarm | inconclusive | reproduced | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calib | planet_deep | 30 | 0.77 | 0.33 | 0 | - | - | - | - | 0.37 | 0.60 | 0 |
| calib | planet_small | 30 | 0.77 | 0.23 | 0 | - | - | - | - | 0.47 | 0.63 | 0 |
| calib | false_positive | 60 | - | - | - | 0.52 | 0.05 | - | - | 0.33 | 0.27 | 0 |
| calib | no_signal | 30 | - | - | - | - | - | 0.47 | 0.00 | 0.33 | 0.03 | 0 |
| dev | planet_deep | 6 | 1.00 | 0.67 | 0 | - | - | - | - | 0.33 | 0.83 | 0 |
| dev | planet_small | 6 | 0.50 | 0.33 | 0 | - | - | - | - | 0.17 | 0.50 | 0 |
| dev | false_positive | 12 | - | - | - | 0.50 | 0.00 | - | - | 0.42 | 0.33 | 0 |
| dev | no_signal | 6 | - | - | - | - | - | 0.50 | 0.00 | 0.33 | 0.00 | 0 |

False positives:

| split | n | rejected, catalog period | rejected, other period | not detected | inconclusive | accepted |
|---|---|---|---|---|---|---|
| calib | 60 | 25 | 6 | 6 | 20 | 3 |
| dev | 12 | 5 | 1 | 1 | 5 | 0 |

Fits:

| split | group | n | failed fits | incomplete |
|---|---|---|---|---|
| calib | planet_deep | 30 | 0 | 0 |
| calib | planet_small | 30 | 0 | 0 |
| calib | false_positive | 60 | 2 | 0 |
| calib | no_signal | 30 | 1 | 0 |
| dev | planet_deep | 6 | 0 | 0 |
| dev | planet_small | 6 | 0 | 0 |
| dev | false_positive | 12 | 1 | 0 |
| dev | no_signal | 6 | 1 | 0 |
