# Phase A: 10-teff-fallback

- code: `c3343e6bc1a12e0f` (before: `ba644a2f971ee844`)
- stars: 180 (calib and dev; the holdout is not read)

## Verdict

- stage: fix
- planets detected on the catalog period: 57 -> 57 (lost 0, gained 0)
- false detections on quiet stars: 5 -> 5
- final recall on planets: 0.347 -> 0.347 (25 -> 25 of 72)
- new accepted false positives: 0
- grave errors: 0 -> 0; new 0
- spurious signals rejected on planet stars: 1 -> 1
- **accepted** by the fix rule

## Before

Planets, calib and dev pooled: final recall 0.347 (25 of 72); accepted false positives 3; grave errors 0 (planets rejected on their catalog period); spurious signals rejected on planet stars 1 (lost detections); false detections on quiet stars 5.

| split | group | n | detection recall | final recall | candidate, wrong period | FP rejected | FP accepted | no_signal | false alarm | inconclusive | reproduced | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calib | planet_deep | 30 | 0.83 | 0.33 | 0 | - | - | - | - | 0.50 | 0.67 | 0 |
| calib | planet_small | 30 | 0.80 | 0.30 | 0 | - | - | - | - | 0.50 | 0.73 | 0 |
| calib | false_positive | 60 | - | - | - | 0.27 | 0.05 | - | - | 0.55 | 0.40 | 0 |
| calib | no_signal | 30 | - | - | - | - | - | 0.87 | 0.00 | 0.07 | 0.03 | 0 |
| dev | planet_deep | 6 | 0.83 | 0.67 | 0 | - | - | - | - | 0.17 | 0.83 | 0 |
| dev | planet_small | 6 | 0.50 | 0.33 | 0 | - | - | - | - | 0.17 | 0.50 | 0 |
| dev | false_positive | 12 | - | - | - | 0.25 | 0.00 | - | - | 0.67 | 0.50 | 0 |
| dev | no_signal | 6 | - | - | - | - | - | 0.83 | 0.00 | 0.17 | 0.00 | 0 |

False positives:

| split | n | rejected, catalog period | rejected, other period | not detected | inconclusive | accepted |
|---|---|---|---|---|---|---|
| calib | 60 | 15 | 1 | 8 | 33 | 3 |
| dev | 12 | 3 | 0 | 1 | 8 | 0 |

Fits:

| split | group | n | failed fits | incomplete |
|---|---|---|---|---|
| calib | planet_deep | 30 | 0 | 0 |
| calib | planet_small | 30 | 0 | 0 |
| calib | false_positive | 60 | 1 | 0 |
| calib | no_signal | 30 | 2 | 0 |
| dev | planet_deep | 6 | 0 | 0 |
| dev | planet_small | 6 | 0 | 0 |
| dev | false_positive | 12 | 0 | 0 |
| dev | no_signal | 6 | 2 | 0 |

## After

Planets, calib and dev pooled: final recall 0.347 (25 of 72); accepted false positives 3; grave errors 0 (planets rejected on their catalog period); spurious signals rejected on planet stars 1 (lost detections); false detections on quiet stars 5.

| split | group | n | detection recall | final recall | candidate, wrong period | FP rejected | FP accepted | no_signal | false alarm | inconclusive | reproduced | incomplete |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calib | planet_deep | 30 | 0.83 | 0.33 | 0 | - | - | - | - | 0.50 | 0.67 | 0 |
| calib | planet_small | 30 | 0.80 | 0.30 | 0 | - | - | - | - | 0.50 | 0.73 | 0 |
| calib | false_positive | 60 | - | - | - | 0.27 | 0.05 | - | - | 0.55 | 0.40 | 0 |
| calib | no_signal | 30 | - | - | - | - | - | 0.87 | 0.00 | 0.07 | 0.03 | 0 |
| dev | planet_deep | 6 | 0.83 | 0.67 | 0 | - | - | - | - | 0.17 | 0.83 | 0 |
| dev | planet_small | 6 | 0.50 | 0.33 | 0 | - | - | - | - | 0.17 | 0.50 | 0 |
| dev | false_positive | 12 | - | - | - | 0.25 | 0.00 | - | - | 0.67 | 0.50 | 0 |
| dev | no_signal | 6 | - | - | - | - | - | 0.83 | 0.00 | 0.17 | 0.00 | 0 |

False positives:

| split | n | rejected, catalog period | rejected, other period | not detected | inconclusive | accepted |
|---|---|---|---|---|---|---|
| calib | 60 | 15 | 1 | 8 | 33 | 3 |
| dev | 12 | 3 | 0 | 1 | 8 | 0 |

Fits:

| split | group | n | failed fits | incomplete |
|---|---|---|---|---|
| calib | planet_deep | 30 | 0 | 0 |
| calib | planet_small | 30 | 0 | 0 |
| calib | false_positive | 60 | 1 | 0 |
| calib | no_signal | 30 | 2 | 0 |
| dev | planet_deep | 6 | 0 | 0 |
| dev | planet_small | 6 | 0 | 0 |
| dev | false_positive | 12 | 0 | 0 |
| dev | no_signal | 6 | 2 | 0 |
