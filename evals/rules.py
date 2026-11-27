"""Phase A of M5: score the baseline on the calibration set and the development split,
and compare two versions of the code that builds dossiers.

    uv run python -m evals.rules [--name NAME] [--before CODE] [--code CODE]

CODE is evals.baseline.code_version() of a run (default: the current one). The holdout
is never read. A rule change is accepted when final recall on planets (calib and dev
pooled) rises, no false positive becomes an accepted candidate and no confirmed planet
becomes a false positive. Reports go in full to <evals_dir>/results/phase-a/<name>.md and
aggregated, without TICs, to evals/results/phase-a-<name>.md.
"""

import argparse
import json
from typing import Any

from evals.baseline import baseline_key, code_version
from evals.index import Index
from evals.paths import REPO, evals_dir
from evals.scorer import table
from evals.scoring import PLANETS, Outcome, period_match, score

SETS = {"v0.1-calib": {"calib"}, "v0.1": {"dev"}}  # never the holdout


def load(code: str) -> tuple[list[dict[str, Any]], dict[int, Outcome]]:
    labels, outcomes = [], {}
    for set_id, splits in SETS.items():
        meta = json.loads((evals_dir() / "sets" / set_id / "set.json").read_text())
        index = Index(evals_dir() / "results" / set_id / "baseline.jsonl")
        found = index.outcomes(baseline_key(meta["set_hash"], code))
        stars = [s for s in meta["stars"] if s["split"] in splits and s["tic_id"] in found]
        labels += stars
        outcomes |= {s["tic_id"]: found[s["tic_id"]] for s in stars}
    return labels, outcomes


def pooled(labels: list[dict], outcomes: dict[int, Outcome]) -> dict[str, Any]:
    """Planets of calib and dev together, and the star sets the acceptance rules watch."""
    planets = [s for s in labels if s["group"] in PLANETS]

    def on_period(s: dict) -> bool:
        return period_match(outcomes[s["tic_id"]].period_days, s["period_days"])

    def final(s: dict) -> str | None:
        return outcomes[s["tic_id"]].final

    ok = [s for s in planets if final(s) == "candidate" and on_period(s)]
    return {
        "planets": len(planets),
        "final_ok": len(ok),
        "final_recall": round(len(ok) / len(planets), 3) if planets else None,
        "accepted_fp": {
            s["tic_id"]
            for s in labels
            if s["group"] == "false_positive" and final(s) == "candidate"
        },
        # grave: a real planet rejected on its catalog period
        "grave": {s["tic_id"] for s in planets if final(s) == "false_positive" and on_period(s)},
        # a spurious signal rejected on a planet's star: a lost detection, not grave
        "spurious": {
            s["tic_id"] for s in planets if final(s) == "false_positive" and not on_period(s)
        },
        "detected": {s["tic_id"] for s in planets if on_period(s)},
        "false_detections": {
            s["tic_id"]
            for s in labels
            if s["group"] == "no_signal" and outcomes[s["tic_id"]].detected
        },
    }


STAGES = ("detection", "vetting", "fix")


def verdict(stage: str, pa: dict[str, Any], pb: dict[str, Any], public: bool) -> list[str]:
    """Detection changes are judged on detection metrics, vetting changes on verdicts, bug
    fixes on doing no harm. A rise in grave errors never reverts on its own: stop and show."""

    def ids(xs: set[int]) -> str:
        return "" if public else f" {sorted(xs)}"

    lost, gained = pb["detected"] - pa["detected"], pa["detected"] - pb["detected"]
    new_fp, new_grave = pa["accepted_fp"] - pb["accepted_fp"], pa["grave"] - pb["grave"]
    fd_b, fd_a = len(pb["false_detections"]), len(pa["false_detections"])
    lines = [
        f"- stage: {stage}",
        f"- planets detected on the catalog period: {len(pb['detected'])} -> "
        f"{len(pa['detected'])} (lost {len(lost)}{ids(lost)}, gained {len(gained)}{ids(gained)})",
        f"- false detections on quiet stars: {fd_b} -> {fd_a}",
        f"- final recall on planets: {pb['final_recall']} -> {pa['final_recall']} "
        f"({pb['final_ok']} -> {pa['final_ok']} of {pa['planets']})",
        f"- new accepted false positives: {len(new_fp)}{ids(new_fp)}",
        f"- grave errors: {len(pb['grave'])} -> {len(pa['grave'])}; new {len(new_grave)}"
        f"{ids(new_grave)}",
        f"- spurious signals rejected on planet stars: {len(pb['spurious'])} -> "
        f"{len(pa['spurious'])}",
    ]
    if stage == "detection":
        better = bool(gained) or fd_a < fd_b
        accepted = not lost and fd_a <= fd_b and better
    elif stage == "vetting":
        accepted = pa["final_ok"] > pb["final_ok"] and not new_fp
    else:  # fix: no metric may get worse
        accepted = not lost and fd_a <= fd_b and pa["final_ok"] >= pb["final_ok"] and not new_fp
    if new_grave:
        lines.append("- **stop**: grave errors rise; show the cause before deciding, do not revert")
    else:
        lines.append(f"- **{'accepted' if accepted else 'not accepted'}** by the {stage} rule")
    return lines


def fp_table(result: dict[str, Any]) -> list[str]:
    lines = [
        "| split | n | rejected, catalog period | rejected, other period | not detected "
        "| inconclusive | accepted |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in result["table"]:
        if row["fp_breakdown"]:
            b = row["fp_breakdown"]
            lines.append(
                f"| {row['split']} | {row['n']} | {b['rejected_catalog_period']} | "
                f"{b['rejected_other_period']} | {b['not_detected']} | "
                f"{b['inconclusive']} | {b['accepted']} |"
            )
    return lines


def fits_table(result: dict[str, Any]) -> list[str]:
    lines = ["| split | group | n | failed fits | incomplete |", "|---|---|---|---|---|"]
    lines += [
        f"| {r['split']} | {r['group']} | {r['n']} | {r['fit_failed']} | {r['incomplete']} |"
        for r in result["table"]
    ]
    return lines


def section(
    title: str, labels: list[dict], outcomes: dict[int, Outcome], public: bool
) -> list[str]:
    result = score(labels, outcomes)
    p = pooled(labels, outcomes)
    out = [
        f"## {title}",
        "",
        f"Planets, calib and dev pooled: final recall {p['final_recall']} "
        f"({p['final_ok']} of {p['planets']}); accepted false positives {len(p['accepted_fp'])}; "
        f"grave errors {len(p['grave'])} (planets rejected on their catalog period); "
        f"spurious signals rejected on planet stars {len(p['spurious'])} (lost detections); "
        f"false detections on quiet stars {len(p['false_detections'])}.",
        "",
    ]
    out += [*table(result, public), "", "False positives:", "", *fp_table(result)]
    out += ["", "Fits:", "", *fits_table(result), ""]
    return out


def report(name: str, code: str, before: str | None, public: bool, stage: str = "vetting") -> str:
    labels, after = load(code)
    out = [
        f"# Phase A: {name}",
        "",
        f"- code: `{code}`" + (f" (before: `{before}`)" if before else ""),
        f"- stars: {len(labels)} (calib and dev; the holdout is not read)",
        "",
    ]
    if before:
        _labels_b, prior = load(before)
        common = [s for s in labels if s["tic_id"] in prior]
        pa, pb = pooled(common, after), pooled(common, prior)
        out += ["## Verdict", "", *verdict(stage, pa, pb, public), ""]
        out += section("Before", common, prior, public)
        out += section("After", common, after, public)
        if not public:
            changed = [
                (s, prior[s["tic_id"]], after[s["tic_id"]])
                for s in common
                if (prior[s["tic_id"]].final, prior[s["tic_id"]].status)
                != (after[s["tic_id"]].final, after[s["tic_id"]].status)
            ]
            out += (
                ["## Stars that changed", ""]
                + [
                    f"- TIC {s['tic_id']} ({s['group']}, {s['split']}): {b.final or b.status} -> "
                    f"{a.final or a.status}"
                    for s, b, a in changed
                ]
                + [""]
            )
    else:
        out += section("Baseline", labels, after, public)
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.rules")
    parser.add_argument("--name", default="current")
    parser.add_argument("--code", default=None, help="default: the current code version")
    parser.add_argument("--before", default=None)
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="vetting",
        help="what the change touches: judged on detection, verdicts, or no harm",
    )
    args = parser.parse_args(argv)
    code = args.code or code_version()
    private_dir = evals_dir() / "results" / "phase-a"
    private_dir.mkdir(parents=True, exist_ok=True)
    text = report(args.name, code, args.before, public=False, stage=args.stage)
    (private_dir / f"{args.name}.md").write_text(text)
    (REPO / "evals" / "results" / f"phase-a-{args.name}.md").write_text(
        report(args.name, code, args.before, public=True, stage=args.stage)
    )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
