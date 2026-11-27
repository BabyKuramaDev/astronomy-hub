"""make eval-baseline: the deterministic pipeline (scripts/build_dossier.py, eval mode)
on every star of the set, locally and without credits.

    uv run python -m evals.baseline [--set v0.1] [--workers 3]

Dossiers go to <evals_dir>/baseline/<set_id>/workspace/w<k> (ignored by that folder's git):
one workspace per worker, because the tools keep numba's compiled kernels per
workspace and parallel processes writing the same cache crash (segfault). A star always
goes to the same worker. Outcomes go
to <evals_dir>/results/<set_id>/baseline.jsonl, keyed on the set hash and the code
trees, so a rerun only does the stars still missing or incomplete. A tool failure that
is not "no data" (a MAST hiccup) is retried once.
"""

import argparse
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

CODE = ("contexts", "shared", "scripts", "missions")  # what can change a dossier


def code_version() -> str:
    """Tree hashes of the code that builds dossiers: commits elsewhere keep the key."""
    trees = subprocess.run(
        ["git", "rev-parse", *(f"HEAD:{d}" for d in CODE)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", *CODE],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return ",".join(t[:12] for t in trees) + ("-dirty" if dirty else "")


def head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def run_star(tic: int, workspace: Path, attempts: int = 2):
    root = workspace / "exoplanets" / str(tic)
    for attempt in range(attempts):
        if root.exists():
            shutil.rmtree(root / "folds", ignore_errors=True)
            for name in (
                "search.json",
                "signal.json",
                "model.json",
                "vetting.json",
                "review.json",
                "decision.json",
                "log.jsonl",
            ):
                (root / name).unlink(missing_ok=True)
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
            }
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.baseline")
    parser.add_argument("--set", default="v0.1", dest="set_id")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    root = evals_dir()
    labels = json.loads((root / "sets" / args.set_id / "set.json").read_text())
    workspaces = root / "baseline" / args.set_id / "workspace"
    index = Index(root / "results" / args.set_id / "baseline.jsonl")
    key = version_key(set_hash=labels["set_hash"], code=code_version(), runner="build_dossier-eval")
    commit = head()
    done = index.done(key, redo_incomplete=True)
    lanes: list[list[int]] = [[] for _ in range(args.workers)]
    for k, star in enumerate(labels["stars"]):  # fixed lane per star, by its place in the set
        if star["tic_id"] not in done:
            lanes[k % args.workers].append(star["tic_id"])
    todo = sum(len(lane) for lane in lanes)
    print(f"baseline: {todo} of {len(labels['stars'])} stars to run", file=sys.stderr)
    finished = [0]
    lock = threading.Lock()

    def lane(k: int) -> None:
        for tic in lanes[k]:
            out, info = run_star(tic, workspaces / f"w{k}")
            index.add(key, out, commit=commit, **info)
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
    print(json.dumps({"key": key, "index": str(index.path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
