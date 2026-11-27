"""Study of the centroid gate (gate 8) on the baseline dossiers; no rule is changed here.

    uv run python -m scripts.centroid_study [--fakes 300]

For the planets the gate fails and the false positives it rejects (calib and dev; the
holdout is not read) it prints the in-transit shift, the depth, the implied offset of
the source (shift / depth: how far from the target a star must sit to make that shift
while carrying the whole dip), the current significance (white-noise error) and an
empirical one: the same measurement at --fakes random false epochs, away from the real
transits, gives the null distribution of the shift, which absorbs correlated noise.
"""

import argparse
import glob
import json
import math
from pathlib import Path

import numpy as np

from contexts.vetting.application.loader import load_inputs
from contexts.vetting.domain.gates import _detrended_centroid
from contexts.vetting.domain.photometry import MeasureParams, windows
from shared.mission import load_mission
from shared.toolkit.dossier import Dossier

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO.parent / "astronomy-hub-evals"
SETS = {"v0.1-calib": "calib", "v0.1": "dev"}
PLANETS = ("planet_deep", "planet_small")


def shift_xy(inputs, epoch: float, duration: float, params: MeasureParams):
    xi, xo, yi, yo = [], [], [], []
    for sector in inputs.raw:
        valid = np.isfinite(sector.centroid_col) & np.isfinite(sector.centroid_row)
        dx = _detrended_centroid(sector.centroid_col, valid)
        dy = _detrended_centroid(sector.centroid_row, valid)
        win = windows(sector.time, inputs.period_days, epoch, duration, params)
        ok = np.isfinite(dx) & np.isfinite(dy)
        xi.append(dx[win.in_transit & ok])
        xo.append(dx[win.baseline & ok])
        yi.append(dy[win.in_transit & ok])
        yo.append(dy[win.baseline & ok])
    xi, xo, yi, yo = (np.concatenate(v) if v else np.array([]) for v in (xi, xo, yi, yo))
    if xi.size < 5 or xo.size < 20:
        return None
    sx = max(float(xo.std() / math.sqrt(xi.size)), 1e-9)
    sy = max(float(yo.std() / math.sqrt(yi.size)), 1e-9)
    return float(xi.mean() - xo.mean()), float(yi.mean() - yo.mean()), sx, sy


def study(root: Path, fakes: int, rng: np.random.Generator) -> dict | None:
    mission = load_mission("exoplanets")
    cfg = mission.vetting
    params = MeasureParams(
        cfg.measurement.duration_scale.default,
        cfg.measurement.window_durations.default,
        cfg.measurement.baseline_inner_durations,
    )
    inputs = load_inputs(Dossier(root), mission.detection.snr_min)
    duration = inputs.duration_hours / 24.0 * params.duration_scale
    real = shift_xy(inputs, inputs.epoch_btjd, duration, params)
    if real is None:
        return None
    mx, my, sx, sy = real
    pix = cfg.gates.centroid.pixel_scale_arcsec
    null = []
    margin = 1.5 * duration / inputs.period_days  # stay clear of the real transits
    for _ in range(fakes):
        phase = rng.uniform(margin, 1.0 - margin)
        r = shift_xy(inputs, inputs.epoch_btjd + phase * inputs.period_days, duration, params)
        if r is not None:
            null.append((r[0], r[1]))
    null = np.array(null)
    zx = (mx - null[:, 0].mean()) / null[:, 0].std()
    zy = (my - null[:, 1].mean()) / null[:, 1].std()
    null_shift = np.hypot(null[:, 0], null[:, 1])
    shift_arcsec = math.hypot(mx, my) * pix
    depth = inputs.depth_ppm * 1e-6
    return {
        "shift_arcsec": round(shift_arcsec, 4),
        "depth_ppm": round(inputs.depth_ppm),
        "offset_arcsec": round(shift_arcsec / depth, 2) if depth > 0 else None,
        "sigma_white": round(math.hypot(mx / sx, my / sy), 1),
        "sigma_empirical": round(math.hypot(zx, zy), 1),
        "p_empirical": round(float(np.mean(null_shift >= math.hypot(mx, my))), 4),
        "n_fakes": len(null),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.centroid_study")
    parser.add_argument("--fakes", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    rng = np.random.default_rng(args.seed)
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
                    / "vetting.json"
                )
            )
            if not found:
                continue
            root = Path(found[0]).parent
            vetting = json.loads((root / "vetting.json").read_text())["data"]
            gates = {g["id"]: g for g in vetting["gates"]}
            if gates.get("centroid", {}).get("status") != "fail":
                continue
            signal = json.loads((root / "signal.json").read_text())["data"]
            catalog = star.get("period_days")
            on_period = bool(catalog) and abs(signal["period_days"] / catalog - 1) <= 0.01
            others = sorted(
                k
                for k, g in gates.items()
                if g["severity"] == "hard" and g["status"] == "fail" and k != "centroid"
            )
            result = study(root, args.fakes, rng)
            if result is None:
                continue
            rows.append(
                {
                    "tic_id": star["tic_id"],
                    "group": star["group"],
                    "split": split,
                    "on_catalog_period": on_period,
                    "other_hard_fails": others,
                    **result,
                }
            )
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
