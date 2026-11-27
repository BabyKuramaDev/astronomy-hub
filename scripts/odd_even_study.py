"""Study of the odd-even gate (gate 5) on the baseline dossiers; no rule is changed here.

    uv run python -m scripts.odd_even_study

For every planet detected on its catalog period and every false positive the gate fails
today (calib and dev; the holdout is not read) it prints the odd and even transit counts
and depths, the current sigma, and a small-sample test: Welch's t with each group's error
taken as the larger of the photometric error and the scatter between its transits, and
the Welch-Satterthwaite degrees of freedom, so that few transits need more evidence.
"""

import glob
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

from contexts.vetting.application.loader import load_inputs
from contexts.vetting.domain.gates import gate_odd_even
from contexts.vetting.domain.photometry import MeasureParams
from shared.kernel.transits import phase_days
from shared.mission import load_mission
from shared.toolkit.dossier import Dossier

EVALS = Path(__file__).resolve().parent.parent.parent / "astronomy-hub-evals"
SETS = {"v0.1-calib": "calib", "v0.1": "dev"}
PLANETS = ("planet_deep", "planet_small")


def group(flux, err, epochs, mask, baseline, min_points=3):
    """Per-transit depths of one parity, and the group's error: max(photometric, scatter)."""
    depths, phot = [], []
    for ep in np.unique(epochs[mask]):
        m = mask & (epochs == ep)
        if m.sum() >= min_points:
            depths.append((baseline - flux[m].mean()) * 1e6)
            phot.append(math.sqrt(float(np.sum(err[m] ** 2))) / m.sum() * 1e6)
    n = len(depths)
    if n < 2:
        return None
    d = np.array(depths)
    se_phot = math.sqrt(float(np.sum(np.square(phot)))) / n
    se_scatter = float(d.std(ddof=1) / math.sqrt(n))
    return {
        "n": n,
        "mean": float(d.mean()),
        "se": max(se_phot, se_scatter),
        "se_phot": se_phot,
        "se_scatter": se_scatter,
    }


def welch(inputs, params):
    duration = inputs.duration_hours / 24.0 * params.duration_scale
    phase = phase_days(inputs.time, inputs.period_days, inputs.epoch_btjd)
    out = np.abs(phase) > duration
    baseline = float(np.median(inputs.flux[out])) if out.any() else 1.0
    core = np.abs(phase) < 0.25 * duration
    epochs = np.rint((inputs.time - inputs.epoch_btjd) / inputs.period_days).astype(np.int64)
    odd = group(inputs.flux, inputs.flux_err, epochs, core & (epochs % 2 == 1), baseline)
    even = group(inputs.flux, inputs.flux_err, epochs, core & (epochs % 2 == 0), baseline)
    if odd is None or even is None:
        return None
    v1, v2 = odd["se"] ** 2, even["se"] ** 2
    t = (odd["mean"] - even["mean"]) / math.sqrt(v1 + v2)
    dof = (v1 + v2) ** 2 / (v1**2 / (odd["n"] - 1) + v2**2 / (even["n"] - 1))
    p = float(2 * stats.t.sf(abs(t), dof))
    return {
        "n_odd": odd["n"],
        "n_even": even["n"],
        "odd_ppm": round(odd["mean"]),
        "even_ppm": round(even["mean"]),
        "t": round(t, 2),
        "dof": round(dof, 1),
        "p_welch": p,
        "z_equiv": round(float(stats.norm.isf(p / 2)), 2),
        "phot_dominates": odd["se_phot"] >= odd["se_scatter"]
        and even["se_phot"] >= even["se_scatter"],
    }


def main() -> int:
    mission = load_mission("exoplanets")
    cfg = mission.vetting
    params = MeasureParams(
        cfg.measurement.duration_scale.default,
        cfg.measurement.window_durations.default,
        cfg.measurement.baseline_inner_durations,
    )
    rows = []
    for set_id, split in SETS.items():
        for star in json.loads((EVALS / "sets" / set_id / "set.json").read_text())["stars"]:
            if star["split"] != split or star["group"] not in (*PLANETS, "false_positive"):
                continue
            found = glob.glob(
                str(
                    EVALS
                    / "baseline"
                    / set_id
                    / "workspace"
                    / "w*"
                    / "exoplanets"
                    / str(star["tic_id"])
                    / "signal.json"
                )
            )
            if not found:
                continue
            root = Path(found[0]).parent
            signal = json.loads((root / "signal.json").read_text())["data"]
            if not signal["detected"]:
                continue
            on_period = abs(signal["period_days"] / star["period_days"] - 1) <= 0.01
            inputs = load_inputs(Dossier(root), mission.detection.snr_min)
            current = gate_odd_even(inputs, params, cfg.gates.odd_even)
            if star["group"] in PLANETS and not on_period:
                continue
            if star["group"] == "false_positive" and current.status != "fail":
                continue
            w = welch(inputs, params)
            if w is None:
                continue
            rows.append(
                {
                    "tic_id": star["tic_id"],
                    "group": star["group"],
                    "split": split,
                    "sigma_now": current.value,
                    "status_now": current.status,
                    **w,
                }
            )
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
