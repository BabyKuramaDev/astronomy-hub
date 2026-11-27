"""Calibrate the detection rule on search.json, without rerunning anything.

    uv run python -m evals.calibrate [--max-false 1] [--exclude-file PATH]

For each candidate statistic (absolute SNR, SNR over the inverted-curve noise floor, SDE)
and each threshold, it replays select-peak: the first peak in rank order whose statistic
reaches the threshold and that has min_transits transits is chosen. A planet counts as
detected when the chosen peak is on its catalog period; a quiet star counts as a false
detection when any peak is chosen. Planets whose catalog period is not among the peaks
are lost in the search, and no threshold can recover them; they are listed apart with
the probable cause. Only the calibration set and the development split are read.
"""

import argparse
import glob
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.paths import evals_dir
from evals.scoring import PLANETS, alias, period_match
from shared.mission import load_mission

SETS = {"v0.1-calib": {"calib"}, "v0.1": {"dev"}}
Stat = Callable[[dict[str, Any], float], float]
STATS: dict[str, Stat] = {
    "snr": lambda peak, floor: peak["snr"],
    "snr_over_floor": lambda peak, floor: peak["snr"] / floor if floor > 0 else float("inf"),
    "sde": lambda peak, floor: peak["sde"],
}


@dataclass(frozen=True)
class Star:
    tic_id: int
    group: str
    split: str
    catalog_period: float | None
    floor: float
    peaks: list[dict[str, Any]]
    discarded: list[dict[str, Any]]


def dossier(set_id: str, tic: int) -> Path | None:
    found = sorted(
        glob.glob(
            str(
                evals_dir()
                / "baseline"
                / set_id
                / "workspace"
                / "w*"
                / "exoplanets"
                / str(tic)
                / "search.json"
            )
        )
    )
    return Path(found[0]).parent if found else None


def load_stars(exclude: set[int]) -> list[Star]:
    stars = []
    for set_id, splits in SETS.items():
        path = evals_dir() / "sets" / set_id / "set.json"
        if not path.exists():
            continue
        meta = json.loads(path.read_text())
        for s in meta["stars"]:
            if s["split"] not in splits or s["tic_id"] in exclude:
                continue
            root = dossier(set_id, s["tic_id"])
            if root is None:
                continue
            search = json.loads((root / "search.json").read_text())["data"]
            stars.append(
                Star(
                    s["tic_id"],
                    s["group"],
                    s["split"],
                    s.get("period_days"),
                    search["inverted_snr_max"],
                    search["peaks"],
                    search["discarded"],
                )
            )
    return stars


def chosen_peak(star: Star, stat: Stat, threshold: float, min_transits: int) -> dict | None:
    for peak in star.peaks:  # rank order, as the Searcher reads them
        if stat(peak, star.floor) >= threshold and peak["n_transits"] >= min_transits:
            return peak
    return None


def lost_cause(star: Star) -> str | None:
    """None when the catalog period is among the peaks; otherwise the probable cause."""
    if any(period_match(p["period_days"], star.catalog_period) for p in star.peaks):
        return None
    for d in star.discarded:
        if period_match(d["period_days"], star.catalog_period):
            return f"discarded as {d['reason']} ({d.get('ratio')} of {d.get('harmonic_of')})"
    for p in star.peaks:
        if (k := alias(p["period_days"], star.catalog_period)) is not None:
            return f"only an alias among the peaks ({k}, {p['id']}, SNR {p['snr']:.1f})"
    best = star.peaks[0]["snr"] if star.peaks else 0.0
    return (
        f"not among the {len(star.peaks)} peaks: likely too shallow for the noise "
        f"(best peak SNR {best:.1f}, floor {star.floor:.1f})"
    )


def sweep(stars: list[Star], name: str, min_transits: int) -> list[dict[str, Any]]:
    stat = STATS[name]
    planets = [s for s in stars if s.group in PLANETS]
    quiet = [s for s in stars if s.group == "no_signal"]
    values = sorted({round(stat(p, s.floor), 3) for s in stars for p in s.peaks})
    rows = []
    for threshold in values:
        hits = sum(
            1
            for s in planets
            if (c := chosen_peak(s, stat, threshold, min_transits)) is not None
            and period_match(c["period_days"], s.catalog_period)
        )
        false = sum(1 for s in quiet if chosen_peak(s, stat, threshold, min_transits) is not None)
        rows.append(
            {
                "threshold": threshold,
                "planets_detected": hits,
                "planets": len(planets),
                "false_detections": false,
                "quiet": len(quiet),
            }
        )
    return rows


def best(rows: list[dict[str, Any]], max_false: int) -> dict[str, Any] | None:
    """Most planets with at most max_false false detections; ties: the highest threshold."""
    ok = [r for r in rows if r["false_detections"] <= max_false]
    return max(ok, key=lambda r: (r["planets_detected"], r["threshold"])) if ok else None


def auc(stars: list[Star], name: str) -> float:
    """Separation of planets (statistic of the catalog-period peak) from quiet stars (best
    statistic of any peak); a planet lost in the search scores 0."""
    stat = STATS[name]
    pos = [
        max(
            (stat(p, s.floor) for p in s.peaks if period_match(p["period_days"], s.catalog_period)),
            default=0.0,
        )
        for s in stars
        if s.group in PLANETS
    ]
    neg = [
        max((stat(p, s.floor) for p in s.peaks), default=0.0)
        for s in stars
        if s.group == "no_signal"
    ]
    pairs = [(1.0 if a > b else 0.5 if a == b else 0.0) for a in pos for b in neg]
    return round(sum(pairs) / len(pairs), 3) if pairs else float("nan")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.calibrate")
    parser.add_argument("--max-false", type=int, default=1)
    parser.add_argument("--exclude", default="", help="comma-separated TICs left out (EBs...)")
    parser.add_argument("--split", choices=["calib", "dev", "all"], default="calib")
    args = parser.parse_args(argv)
    detection = load_mission("exoplanets").detection
    exclude = {int(x) for x in args.exclude.split(",") if x}
    stars = [s for s in load_stars(exclude) if args.split in ("all", s.split)]
    out: dict[str, Any] = {
        "split": args.split,
        "excluded": sorted(exclude),
        "counts": {
            g: sum(s.group == g for s in stars)
            for g in ("planet_deep", "planet_small", "no_signal")
        },
    }
    current = {"stat": "snr", "threshold": detection.snr_min}
    out["current"] = (
        next(
            r
            for r in sweep(stars, "snr", detection.min_transits)
            if r["threshold"] >= detection.snr_min
        )
        | current
    )
    out["stats"] = {}
    for name in STATS:
        rows = sweep(stars, name, detection.min_transits)
        out["stats"][name] = {"auc": auc(stars, name), "best": best(rows, args.max_false)}
    lost = [
        {"tic_id": s.tic_id, "group": s.group, "split": s.split, "cause": c}
        for s in stars
        if s.group in PLANETS and (c := lost_cause(s)) is not None
    ]
    out["lost_in_search"] = lost
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
