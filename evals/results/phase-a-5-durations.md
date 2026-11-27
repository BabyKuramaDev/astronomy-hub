# Phase A: 5-durations

- code: `f33a992669fe27d5` (before: `913ffa01690ea5f2`)
- stars: 180 (calib and dev; the holdout is not read)

## Verdict

- stage: detection
- planets detected on the catalog period: 55 -> 56 (lost 0, gained 1)
- false detections on quiet stars: 19 -> 19
- final recall on planets: 0.319 -> 0.319 (23 -> 23 of 72)
- new accepted false positives: 0
- grave errors: 5 -> 6; new 1
- spurious signals rejected on planet stars: 6 -> 5
- **stop**: grave errors rise; show the cause before deciding, do not revert

## Before

Planets, calib and dev pooled: final recall 0.319 (23 of 72); accepted false positives 3; grave errors 5 (planets rejected on their catalog period); spurious signals rejected on planet stars 6 (lost detections); false detections on quiet stars 19.

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

## After

Planets, calib and dev pooled: final recall 0.319 (23 of 72); accepted false positives 3; grave errors 6 (planets rejected on their catalog period); spurious signals rejected on planet stars 5 (lost detections); false detections on quiet stars 19.

| split | group | n | detection recall | final recall | candidate, wrong period | FP rejected | FP accepted | no_signal | false alarm | inconclusive | reproduced | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calib | planet_deep | 30 | 0.77 | 0.33 | 0 | - | - | - | - | 0.37 | 0.60 | 0 |
| calib | planet_small | 30 | 0.80 | 0.23 | 0 | - | - | - | - | 0.47 | 0.63 | 0 |
| calib | false_positive | 60 | - | - | - | 0.47 | 0.05 | - | - | 0.38 | 0.27 | 0 |
| calib | no_signal | 30 | - | - | - | - | - | 0.47 | 0.00 | 0.33 | 0.03 | 0 |
| dev | planet_deep | 6 | 1.00 | 0.67 | 0 | - | - | - | - | 0.33 | 0.83 | 0 |
| dev | planet_small | 6 | 0.50 | 0.33 | 0 | - | - | - | - | 0.17 | 0.50 | 0 |
| dev | false_positive | 12 | - | - | - | 0.42 | 0.00 | - | - | 0.50 | 0.33 | 0 |
| dev | no_signal | 6 | - | - | - | - | - | 0.50 | 0.00 | 0.50 | 0.00 | 0 |

False positives:

| split | n | rejected, catalog period | rejected, other period | not detected | inconclusive | accepted |
|---|---|---|---|---|---|---|
| calib | 60 | 25 | 3 | 6 | 23 | 3 |
| dev | 12 | 5 | 0 | 1 | 6 | 0 |

Fits:

| split | group | n | failed fits | incomplete |
|---|---|---|---|---|
| calib | planet_deep | 30 | 0 | 0 |
| calib | planet_small | 30 | 0 | 0 |
| calib | false_positive | 60 | 1 | 0 |
| calib | no_signal | 30 | 0 | 0 |
| dev | planet_deep | 6 | 0 | 0 |
| dev | planet_small | 6 | 0 | 0 |
| dev | false_positive | 12 | 0 | 0 |
| dev | no_signal | 6 | 1 | 0 |
