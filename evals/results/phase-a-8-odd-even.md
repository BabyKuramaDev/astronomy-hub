# Phase A: 8-odd-even

- code: `a6e4d58fc8543379` (before: `84681733c0b3275f`)
- stars: 180 (calib and dev; the holdout is not read)

## Verdict

- stage: vetting
- planets detected on the catalog period: 56 -> 56 (lost 0, gained 0)
- false detections on quiet stars: 19 -> 19
- final recall on planets: 0.333 -> 0.347 (24 -> 25 of 72)
- new accepted false positives: 0
- grave errors: 3 -> 0; new 0
- spurious signals rejected on planet stars: 3 -> 3
- **accepted** by the vetting rule

## Before

Planets, calib and dev pooled: final recall 0.333 (24 of 72); accepted false positives 3; grave errors 3 (planets rejected on their catalog period); spurious signals rejected on planet stars 3 (lost detections); false detections on quiet stars 19.

| split | group | n | detection recall | final recall | candidate, wrong period | FP rejected | FP accepted | no_signal | false alarm | inconclusive | reproduced | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calib | planet_deep | 30 | 0.77 | 0.33 | 0 | - | - | - | - | 0.43 | 0.63 | 0 |
| calib | planet_small | 30 | 0.80 | 0.27 | 0 | - | - | - | - | 0.53 | 0.70 | 0 |
| calib | false_positive | 60 | - | - | - | 0.28 | 0.05 | - | - | 0.57 | 0.40 | 0 |
| calib | no_signal | 30 | - | - | - | - | - | 0.47 | 0.00 | 0.40 | 0.03 | 0 |
| dev | planet_deep | 6 | 1.00 | 0.67 | 0 | - | - | - | - | 0.33 | 0.83 | 0 |
| dev | planet_small | 6 | 0.50 | 0.33 | 0 | - | - | - | - | 0.17 | 0.50 | 0 |
| dev | false_positive | 12 | - | - | - | 0.25 | 0.00 | - | - | 0.67 | 0.50 | 0 |
| dev | no_signal | 6 | - | - | - | - | - | 0.50 | 0.00 | 0.50 | 0.00 | 0 |

False positives:

| split | n | rejected, catalog period | rejected, other period | not detected | inconclusive | accepted |
|---|---|---|---|---|---|---|
| calib | 60 | 16 | 1 | 6 | 34 | 3 |
| dev | 12 | 3 | 0 | 1 | 8 | 0 |

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

## After

Planets, calib and dev pooled: final recall 0.347 (25 of 72); accepted false positives 3; grave errors 0 (planets rejected on their catalog period); spurious signals rejected on planet stars 3 (lost detections); false detections on quiet stars 19.

| split | group | n | detection recall | final recall | candidate, wrong period | FP rejected | FP accepted | no_signal | false alarm | inconclusive | reproduced | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calib | planet_deep | 30 | 0.77 | 0.33 | 0 | - | - | - | - | 0.47 | 0.63 | 0 |
| calib | planet_small | 30 | 0.80 | 0.30 | 0 | - | - | - | - | 0.57 | 0.77 | 0 |
| calib | false_positive | 60 | - | - | - | 0.27 | 0.05 | - | - | 0.58 | 0.42 | 0 |
| calib | no_signal | 30 | - | - | - | - | - | 0.47 | 0.00 | 0.40 | 0.03 | 0 |
| dev | planet_deep | 6 | 1.00 | 0.67 | 0 | - | - | - | - | 0.33 | 0.83 | 0 |
| dev | planet_small | 6 | 0.50 | 0.33 | 0 | - | - | - | - | 0.17 | 0.50 | 0 |
| dev | false_positive | 12 | - | - | - | 0.25 | 0.00 | - | - | 0.67 | 0.50 | 0 |
| dev | no_signal | 6 | - | - | - | - | - | 0.50 | 0.00 | 0.50 | 0.00 | 0 |

False positives:

| split | n | rejected, catalog period | rejected, other period | not detected | inconclusive | accepted |
|---|---|---|---|---|---|---|
| calib | 60 | 15 | 1 | 6 | 35 | 3 |
| dev | 12 | 3 | 0 | 1 | 8 | 0 |

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
