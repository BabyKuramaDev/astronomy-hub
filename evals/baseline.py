"""make eval-baseline: the deterministic pipeline (scripts/build_dossier.py, eval mode)
on every star of the set, locally and without credits.

    uv run python -m evals.baseline [--set v0.1] [--workers 3]

Dossiers go to <evals_dir>/baseline/<set_id>/workspace (ignored by that folder's git);
outcomes to <evals_dir>/results/<set_id>/baseline.jsonl, keyed on the set hash and the
repository commit, so a rerun only does the stars still missing. A tool failure that
is not "no data" (a MAST hiccup) is retried once.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from evals.index import Index, version_key
from evals.outcomes import from_dossier
from evals.paths import REPO, evals_dir


def commit() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "contexts", "shared", "scripts", "missions"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


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
    workspace = root / "baseline" / args.set_id / "workspace"
    index = Index(root / "results" / args.set_id / "baseline.jsonl")
    key = version_key(set_hash=labels["set_hash"], commit=commit(), runner="build_dossier-eval")
    todo = [s["tic_id"] for s in labels["stars"] if s["tic_id"] not in index.done(key)]
    print(f"baseline: {len(todo)} of {len(labels['stars'])} stars to run", file=sys.stderr)
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(run_star, tic, workspace): tic for tic in todo}
        for k, future in enumerate(as_completed(futures), 1):
            out, info = future.result()
            index.add(key, out, **info)
            print(
                f"[{k}/{len(todo)}] TIC {out.tic_id}: {out.status} {out.final or ''} "
                f"{out.active_seconds:.0f}s",
                file=sys.stderr,
            )
    print(json.dumps({"key": key, "index": str(index.path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
