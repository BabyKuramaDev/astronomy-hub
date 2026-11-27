"""make eval-baseline: the deterministic pipeline (scripts/build_dossier.py, eval mode)
on the stars of a set, locally and without credits.

    uv run python -m evals.baseline [--set v0.1] [--splits dev] [--from STAGE] [--workers 3]

Dossiers go to <evals_dir>/baseline/<set_id>/workspace/w<k> (ignored by that folder's git):
one workspace per worker, because the tools keep numba's compiled kernels per
workspace and parallel processes writing the same cache crash (segfault). A star always
goes to the same worker. Outcomes go to <evals_dir>/results/<set_id>/baseline.jsonl,
keyed on the set hash and the code that builds dossiers, so a rerun only does the stars
still missing or incomplete.

--from reruns only the stages a change touches (select, fit, vetting, review), reading
the earlier ones from each dossier; the files of that stage and later are deleted
first. The holdout split never runs unless --splits names it.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from evals.index import Index, version_key
from evals.outcomes import from_dossier
from evals.paths import REPO, evals_dir

CODE = ("contexts", "shared", "missions", "scripts/build_dossier.py", "uv.lock")
STAGES = ("start", "select", "fit", "vetting", "review")
REVIEW = ["review.json", "review", "decision.json"]
VETTING = ["vetting.json", "vetting", *REVIEW]
FIT = ["model.json", *VETTING]
SELECT = ["signal.json", "folds", "figures", *FIT]
CLEAR = {
    "start": ["search.json", *SELECT, "log.jsonl"],
    "select": SELECT,
    "fit": FIT,
    "vetting": VETTING,
    "review": REVIEW,
}


def _builds_dossiers(path: str) -> bool:
    """Python code, the mission and the locked dependencies; agent prompts do not count."""
    return path.endswith(".py") or path.startswith("missions/") or path in CODE


def code_version() -> str:
    """Hash of the files that build a dossier: commits elsewhere keep the key."""
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--", *CODE],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    files = sorted(
        line.split()[2] + " " + line.split("\t")[1]
        for line in listing
        if _builds_dossiers(line.split("\t")[1])
    )
    digest = hashlib.sha256("\n".join(files).encode()).hexdigest()[:16]
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", *CODE],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return digest + ("-dirty" if any(_builds_dossiers(x[3:]) for x in dirty) else "")


def head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def baseline_key(set_hash: str, code: str) -> str:
    return version_key(set_hash=set_hash, code=code, runner="build_dossier-eval")


def clear(root: Path, stage: str) -> None:
    for name in CLEAR[stage]:
        path = root / name
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def run_star(tic: int, workspace: Path, stage: str = "start", attempts: int = 2):
    root = workspace / "exoplanets" / str(tic)
    if stage != "start" and not (root / "search.json").exists():
        stage = "start"  # nothing to resume from
    for attempt in range(attempts):
        if root.exists():
            clear(root, stage)
        started = time.monotonic()
        argv = [
            sys.executable,
            "-m",
            "scripts.build_dossier",
            "--tic",
            str(tic),
            "--mode",
            "eval",
            "--workspace",
            str(workspace),
            "--from",
            stage,
        ]
        proc = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, check=False)
        seconds = round(time.monotonic() - started, 1)
        out = from_dossier(tic, root, active_seconds=seconds)
        if out.status != "incomplete" or attempt == attempts - 1:
            tail = proc.stderr.strip().splitlines()[-1:] if proc.returncode else []
            return out, {
                "exit": proc.returncode,
                "error": tail[0] if tail else None,
                "attempts": attempt + 1,
                "stage": stage,
            }
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.baseline")
    parser.add_argument("--set", default="v0.1", dest="set_id")
    parser.add_argument(
        "--splits",
        default="dev,calib",
        help="comma-separated splits to run (holdout only if named)",
    )
    parser.add_argument("--from", dest="from_stage", choices=STAGES, default="start")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    root = evals_dir()
    labels = json.loads((root / "sets" / args.set_id / "set.json").read_text())
    splits = set(args.splits.split(","))
    workspaces = root / "baseline" / args.set_id / "workspace"
    index = Index(root / "results" / args.set_id / "baseline.jsonl")
    code = code_version()
    key = baseline_key(labels["set_hash"], code)
    done = index.done(key, redo_incomplete=True)
    lanes: list[list[int]] = [[] for _ in range(args.workers)]
    for k, star in enumerate(labels["stars"]):  # fixed lane per star, by its place in the set
        if star["split"] in splits and star["tic_id"] not in done:
            lanes[k % args.workers].append(star["tic_id"])
    todo = sum(len(lane) for lane in lanes)
    print(
        f"baseline {args.set_id} {sorted(splits)} from {args.from_stage}: {todo} stars to run",
        file=sys.stderr,
    )
    commit, finished, lock = head(), [0], threading.Lock()

    def lane(k: int) -> None:
        for tic in lanes[k]:
            out, info = run_star(tic, workspaces / f"w{k}", args.from_stage)
            index.add(key, out, commit=commit, code=code, **info)
            with lock:
                finished[0] += 1
                print(
                    f"[{finished[0]}/{todo}] TIC {out.tic_id}: {out.status} {out.final or ''} "
                    f"{out.active_seconds:.0f}s",
                    file=sys.stderr,
                    flush=True,
                )

    with ThreadPoolExecutor(args.workers) as pool:
        for future in [pool.submit(lane, k) for k in range(args.workers)]:
            future.result()
    print(json.dumps({"key": key, "code": code, "index": str(index.path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
