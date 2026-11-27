# Phase A: antes

- code: `1538dce36e1e1637`
- stars: 180 (calib and dev; the holdout is not read)

## Baseline

Planets, calib and dev pooled: final recall 0.264 (19 of 72); accepted false positives 3; grave errors 11 (5 on the catalog period, the rest on another signal).

| split | group | n | detection recall | final recall | candidate, wrong period | FP rejected | FP accepted | no_signal | false alarm | inconclusive | reproduced | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calib | planet_deep | 30 | 0.77 | 0.27 | 0 | - | - | - | - | 0.43 | 0.43 | 0 |
| calib | planet_small | 30 | 0.77 | 0.23 | 0 | - | - | - | - | 0.47 | 0.60 | 0 |
| calib | false_positive | 60 | - | - | - | 0.48 | 0.05 | - | - | 0.32 | 0.25 | 3 |
| calib | no_signal | 30 | - | - | - | - | - | 0.47 | 0.00 | 0.30 | 0.03 | 2 |
| dev | planet_deep | 6 | 1.00 | 0.33 | 0 | - | - | - | - | 0.67 | 0.50 | 0 |
| dev | planet_small | 6 | 0.50 | 0.33 | 0 | - | - | - | - | 0.17 | 0.50 | 0 |
| dev | false_positive | 12 | - | - | - | 0.50 | 0.00 | - | - | 0.42 | 0.25 | 0 |
| dev | no_signal | 6 | - | - | - | - | - | 0.50 | 0.00 | 0.17 | 0.00 | 2 |

False positives:

| split | n | rejected, catalog period | rejected, other period | not detected | inconclusive | accepted |
|---|---|---|---|---|---|---|
| calib | 60 | 24 | 5 | 6 | 19 | 3 |
| dev | 12 | 5 | 1 | 1 | 5 | 0 |

Fits:

| split | group | n | failed fits | incomplete |
|---|---|---|---|---|
| calib | planet_deep | 30 | 0 | 0 |
| calib | planet_small | 30 | 0 | 0 |
| calib | false_positive | 60 | 3 | 3 |
| calib | no_signal | 30 | 2 | 2 |
| dev | planet_deep | 6 | 0 | 0 |
| dev | planet_small | 6 | 0 | 0 |
| dev | false_positive | 12 | 0 | 0 |
| dev | no_signal | 6 | 2 | 2 |
