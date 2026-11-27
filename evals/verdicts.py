"""Inconclusive causes and alternative verdict rules, on the saved baseline dossiers.

    uv run python -m evals.verdicts

Nothing is rerun: it reads vetting.json, review.json and signal.json of the calibration
set and the development split (the holdout is not read). For every inconclusive star it
lists what kept it there (a hard gate marginal, a soft gate failing, a soft gate marginal,
the Reviewer not reproducing). Then it scores two verdict rules:
  a. current: candidate when every gate passes and the Reviewer reproduces;
  b. two tiers: A as (a); B when no hard gate fails or is marginal, no soft gate fails,
     the Reviewer reproduces and the only non-passing gates are soft marginals.
"""

import glob
import json
from collections import Counter
from pathlib import Path
from typing import Any

from evals.paths import evals_dir
from evals.scoring import PLANETS, period_match

SETS = {"v0.1-calib": "calib", "v0.1": "dev"}


def stars() -> list[dict[str, Any]]:
    out = []
    for set_id, split in SETS.items():
        for s in json.loads((evals_dir() / "sets" / set_id / "set.json").read_text())["stars"]:
            if s["split"] != split:
                continue
            found = glob.glob(
                str(
                    evals_dir()
                    / "baseline"
                    / set_id
                    / "workspace"
                    / "w*"
                    / "exoplanets"
                    / str(s["tic_id"])
                    / "decision.json"
                )
            )
            if not found:
                continue
            root = Path(found[0]).parent

            def data(name: str, root: Path = root) -> dict | None:
                p = root / name
                return json.loads(p.read_text())["data"] if p.exists() else None

            out.append(
                {
                    **s,
                    "decision": data("decision.json"),
                    "signal": data("signal.json"),
                    "vetting": data("vetting.json"),
                    "review": data("review.json"),
                }
            )
    return out


def gates_by(star: dict, status: str, severity: str) -> list[str]:
    v = star["vetting"]
    if v is None:
        return []
    return sorted(
        g["id"] for g in v["gates"] if g["status"] == status and g["severity"] == severity
    )


def tier(star: dict) -> str:
    """Final verdict under rule (b): A, B, or the current non-candidate verdict."""
    final = star["decision"]["final"]
    if final == "candidate":
        return "A"
    if final != "inconclusive" or star["vetting"] is None:
        return final
    reproduced = (star["review"] or {}).get("verdict") == "reproduced"
    hard = gates_by(star, "fail", "hard") + gates_by(star, "marginal", "hard")
    soft_fail = gates_by(star, "fail", "soft")
    soft_marginal = gates_by(star, "marginal", "soft")
    if reproduced and not hard and not soft_fail and soft_marginal:
        return "B"
    return "inconclusive"


REASONS = (  # (gate, note fragment, short reason)
    ("odd-even", "fewer than two odd or two even", "fewer than 2 odd or even transits"),
    ("odd-even", "Welch", "Welch p below marginal_p"),
    ("holdout", "needs at least two sectors", "a single sector"),
    ("holdout", "fewer than two sectors cover", "fewer than 2 sectors with a transit"),
    ("holdout", "held-out sectors", "Z below the thresholds"),
    ("coverage", "need at least", "fewer than min_transits transits"),
    ("plausibility", "failed fit", "failed fit"),
    ("plausibility", "nothing to check", "no stellar radius or mass"),
    ("plausibility", "bigger than 99%", "radius above the 99th percentile"),
    ("plausibility", "crosses", "radius interval crosses the maximum"),
    ("centroid", "no catalogued neighbor", "shift without a possible source"),
    ("centroid", "would need", "shift below fail_sigma with a possible source"),
    ("centroid", "not enough centroid", "too few centroid points"),
    ("secondary", "not by", "above the bound without the margin"),
    ("secondary", "fewer than two primary", "too few events"),
)


def reason(gate: dict) -> str:
    for gid, fragment, short in REASONS:
        if gate["id"] == gid and fragment in gate["note"]:
            return short
    return "other"


def causes(star: dict) -> list[str]:
    v = star["vetting"] or {"gates": []}
    out = [
        f"{g['severity']} {g['status']}: {g['id']} ({reason(g)})"
        for g in v["gates"]
        if g["severity"] in ("hard", "soft")
        and g["status"] in ("fail", "marginal")
        and not (g["severity"] == "hard" and g["status"] == "fail")
    ]
    review = (star["review"] or {}).get("verdict")
    if review and review != "reproduced":
        out.append(f"review {review}")
    return out


def main() -> int:
    data = stars()
    groups = ("planet_deep", "planet_small", "false_positive", "no_signal")
    print("# Inconclusive stars by cause (a star can have several)\n")
    for split in ("calib", "dev"):
        for group in groups:
            inc = [
                s
                for s in data
                if s["split"] == split
                and s["group"] == group
                and s["decision"]["final"] == "inconclusive"
            ]
            if not inc:
                continue
            c = Counter(x for s in inc for x in causes(s))
            print(f"{split} {group}: {len(inc)} inconclusive")
            for cause, n in c.most_common():
                print(f"    {n:>3}  {cause}")
    print("\n# Verdict rules\n")
    print(
        "| split | rule | tier | planets on period | final recall | deep | small | "
        "FP accepted | quiet false alarms |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for split in ("calib", "dev"):
        sub = [s for s in data if s["split"] == split]
        planets = [s for s in sub if s["group"] in PLANETS]
        for rule, tiers in (("a", ("A",)), ("b", ("A",)), ("b", ("A", "B"))):

            def ok(s: dict, tiers: tuple = tiers) -> bool:
                return tier(s) in tiers

            def on_period(s: dict) -> bool:
                return bool(
                    s["signal"]
                    and s["signal"]["detected"]
                    and period_match(s["signal"]["period_days"], s["period_days"])
                )

            hit = [s for s in planets if ok(s) and on_period(s)]
            deep = sum(s["group"] == "planet_deep" for s in hit)
            small = sum(s["group"] == "planet_small" for s in hit)
            n_deep = sum(s["group"] == "planet_deep" for s in planets)
            n_small = len(planets) - n_deep
            fp = [s for s in sub if s["group"] == "false_positive" and ok(s)]
            quiet = [s for s in sub if s["group"] == "no_signal" and ok(s)]
            label = "+".join(tiers)
            print(
                f"| {split} | {rule} | {label} | {len(planets)} | "
                f"{len(hit) / len(planets):.2f} ({len(hit)}) | {deep}/{n_deep} | "
                f"{small}/{n_small} | {len(fp)} | {len(quiet)} |"
            )
    b_fp = [s["tic_id"] for s in data if s["group"] == "false_positive" and tier(s) == "B"]
    print(f"\nFalse positives that tier B would accept: {b_fp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
