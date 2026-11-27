"""Score the baseline or the agent runs of an eval set and write the reports.

    uv run python -m evals.scorer baseline [--set v0.1]
    uv run python -m evals.scorer agents [--set v0.1] [--compare]

Each report goes twice: in full (with TICs) to <evals_dir>/results/<set>/<kind>.md, and
aggregated only (no TICs, nothing that names a star) to evals/results/<set>-<kind>.md
in this repository. The outcomes are those of the latest version key in the index.
"""

import argparse
import json
import sys
from typing import Any

from evals.index import Index
from evals.paths import REPO, evals_dir
from evals.scoring import compare, score

COLUMNS = [
    ("split", "split"),
    ("group", "group"),
    ("n", "n"),
    ("detection_recall", "detection recall"),
    ("final_recall", "final recall"),
    ("candidate_wrong_period", "candidate, wrong period"),
    ("false_positive_rejected", "FP rejected"),
    ("false_positive_accepted", "FP accepted"),
    ("no_signal_correct", "no_signal"),
    ("false_alarm", "false alarm"),
    ("inconclusive", "inconclusive"),
    ("reproduced", "reproduced"),
    ("incomplete", "incomplete"),
]


def latest(index: Index) -> tuple[str, list[dict[str, Any]]]:
    rows = index.rows()
    if not rows:
        raise SystemExit(f"{index.path} is empty: run the stars first")
    key = rows[-1]["key"]
    return key, [r for r in rows if r["key"] == key]


def table(result: dict[str, Any], public: bool) -> list[str]:
    lines = ["| " + " | ".join(h for _, h in COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for row in result["table"]:
        cells = []
        for k, _ in COLUMNS:
            v = row[k]
            cells.append("-" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    if not public:
        quiet = [t for r in result["table"] for t in r["detections_to_review"]]
        lines += ["", f"Detections on quiet stars, to review by hand: {quiet or 'none'}"]
    return lines


def listing(title: str, items: list[dict[str, Any]], public: bool) -> list[str]:
    if public:
        return [f"- {title}: {len(items)}"]
    return [f"- {title}: {len(items)}"] + [f"  - {json.dumps(i, sort_keys=True)}" for i in items]


def report(
    kind: str,
    labels: dict,
    key: str,
    rows: list[dict],
    result: dict,
    diff: list[dict] | None,
    public: bool,
) -> str:
    commits = sorted({r.get("commit", "?")[:12] for r in rows})
    out = [
        f"# Eval {labels['set_id']}: {kind}",
        "",
        f"- set hash: `{labels['set_hash']}`",
        f"- version key: `{key}`",
        f"- commits: {', '.join(commits)}",
        f"- stars scored: {len(result['rows'])}",
    ]
    versions = rows[-1].get("versions")
    if versions:
        agents = ", ".join(
            f"{k.removeprefix('./contexts/').removesuffix('.md')} v{v[1]}"
            for k, v in versions["agents"].items()
        )
        out += [f"- agents: {agents}", f"- eval environment: {versions['environment'][0]}"]
    cost = result["cost"]
    out += [
        f"- cost: {cost['total_cents'] / 100:.2f} USD in all, "
        f"{(cost['per_star_cents'] or 0) / 100:.2f} USD per star; "
        f"{cost['active_seconds_per_star']} s per star",
        "",
        "## Metrics",
        "",
    ]
    out += table(result, public)
    out += ["", "## Apart", ""]
    out += listing(
        "grave errors (confirmed planet -> false_positive)", result["grave_errors"], public
    )
    out += listing("aliases of the catalog period", result["aliases"], public)
    out += listing("contaminated or without data (not failures)", result["apart"], public)
    if diff is not None:
        better = sum(d["effect"] == "better" for d in diff)
        worse = sum(d["effect"] == "worse" for d in diff)
        out += [
            "",
            "## Agents against the baseline",
            "",
            f"Stars where the agents chose differently: {len(diff)} "
            f"({better} better, {worse} worse, {len(diff) - better - worse} same grade)",
        ]
        if not public:
            out += [""] + [
                f"- TIC {d['tic_id']} ({d['group']}): {d['effect']}; agents "
                f"{d['agent']}, script {d['baseline']}"
                for d in diff
            ]
    if not public:
        out += [
            "",
            "## Stars",
            "",
            "| TIC | group | split | status | final | period | catalog "
            "| grade | cost | s | flags |",
            "|" + "---|" * 11,
        ]
        for r in sorted(result["rows"], key=lambda r: (r["group"], r["tic_id"])):
            out.append(
                f"| {r['tic_id']} | {r['group']} | {r['split']} | {r['status']} | "
                f"{r['final']} | {r['period_days']} | {r['catalog_period']} | {r['grade']} "
                f"| {r['cost_cents'] / 100:.2f} | {r['active_seconds']:.0f} | {r['flags']} |"
            )
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.scorer")
    parser.add_argument("kind", choices=["baseline", "agents"])
    parser.add_argument("--set", default="v0.1", dest="set_id")
    parser.add_argument("--compare", action="store_true", help="agents only: against the baseline")
    parser.add_argument("--splits", default="calib,dev", help="holdout only when named")
    args = parser.parse_args(argv)
    root = evals_dir() / "results" / args.set_id
    labels = json.loads((evals_dir() / "sets" / args.set_id / "set.json").read_text())
    key, rows = latest(Index(root / f"{args.kind}.jsonl"))
    outcomes = Index(root / f"{args.kind}.jsonl").outcomes(key)
    splits = set(args.splits.split(","))
    stars = [s for s in labels["stars"] if s["tic_id"] in outcomes and s["split"] in splits]
    rows = [r for r in rows if r["tic_id"] in {s["tic_id"] for s in stars}]
    result = score(stars, outcomes)
    diff = None
    if args.compare and args.kind == "agents":
        base_index = Index(root / "baseline.jsonl")
        base_key, _ = latest(base_index)
        diff = compare(stars, outcomes, base_index.outcomes(base_key))
    private = report(args.kind, labels, key, rows, result, diff, public=False)
    public = report(args.kind, labels, key, rows, result, diff, public=True)
    (root / f"{args.kind}.md").write_text(private)
    (root / f"{args.kind}.json").write_text(
        json.dumps({"key": key, **result, "compare": diff}, indent=1, sort_keys=True) + "\n"
    )
    public_dir = REPO / "evals" / "results"
    public_dir.mkdir(exist_ok=True)
    (public_dir / f"{args.set_id}-{args.kind}.md").write_text(public)
    print(private, file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
