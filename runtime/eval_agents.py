"""make eval-pilot / make eval-dev: run eval-set stars on Managed Agents (eval profile).

    uv run python -m runtime.eval_agents --pilot --cap-cents 1000
    uv run python -m runtime.eval_agents --split dev --milestone M4-dev --cap-cents N

Resumable: a star already in <evals_dir>/results/<set>/agents.jsonl under the same key
(set hash, every agent version, the eval environment and the code trees the session
clones) is skipped. Only platform failures (the session ended without settling) and
MAST errors are retried, once. A session that runs out of budget is not retried.
Sessions run in parallel (3 by default); the spend cap counts the budgets in flight.
"""

import argparse
import json
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from evals.index import Index, version_key
from evals.outcomes import from_agent_run
from evals.paths import evals_dir
from evals.scoring import Outcome
from evals.selection import pilot
from runtime.checks import agent_names
from runtime.ledger import SpendCapError, check_cap, spent_cents
from runtime.managed import ManagedAgentsRuntime, RunConfig
from runtime.repo import LOCK, REPO, REPO_URL, RepoStateError, pinned_commit, resource

RUNS = REPO / "runs"
SANDBOX_CODE = ("bin", "contexts", "shared", "scripts", "missions")
PLATFORM_STOPS = {"terminated", "stream_lost", "retries_exhausted"}
MAST_ERROR = re.compile(
    r"fetch-lightcurves.{0,400}?(HTTPError|ConnectionError|Timeout|RemoteDisconnected"
    r"|ServiceUnavailable|exit(ed)? (code )?1\b)",
    re.S,
)
NO_DATA = re.compile(r"no SPOC 120 s light curves|download returned no file|no valid cadences")


def versions() -> dict[str, Any]:
    lock = json.loads(LOCK.read_text())["resources"]
    agents = {
        k: (v["id"], v.get("version"))
        for k, v in sorted(lock.items())
        if k.endswith("agent.md") and "probe" not in k
    }
    env = lock["./environment_eval.yaml"]
    trees = subprocess.run(
        ["git", "rev-parse", *(f"HEAD:{d}" for d in SANDBOX_CODE), "HEAD:uv.lock"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return {
        "agents": agents,
        "environment": (env["id"], env.get("version")),
        "code": ",".join(t[:12] for t in trees),
    }


@dataclass
class Budget:
    """Reserve a session's budget against the cap before it starts."""

    ledger: Path
    cap_cents: int
    budget_cents: int
    milestone: str
    in_flight: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self) -> int:
        with self.lock:
            check_cap(
                self.ledger, self.cap_cents, self.budget_cents, self.milestone, self.in_flight
            )
            reserved = self.in_flight
            self.in_flight += self.budget_cents
            return reserved

    def release(self) -> None:
        with self.lock:
            self.in_flight -= self.budget_cents


def retryable(summary: dict[str, Any], out: Outcome, events: str) -> bool:
    if out.status != "incomplete":
        return False
    return summary["stop_reason"] in PLATFORM_STOPS or bool(MAST_ERROR.search(events))


def run_star(tic: int, base: RunConfig, budget: Budget, retries: int) -> tuple[Outcome, dict]:
    from runtime.platform import ManagedAgentsPlatform

    attempts = []
    for attempt in range(retries + 1):
        reserved = budget.reserve()
        try:
            cfg = RunConfig(**{**base.__dict__, "reserved_cents": reserved})
            result = ManagedAgentsRuntime(ManagedAgentsPlatform(), cfg).run(
                tic, "exoplanets", "eval", budget.budget_cents
            )
        finally:
            budget.release()
        summary = json.loads(result.summary_file.read_text())
        events = (result.summary_file.parent / "events.jsonl").read_text()
        out = from_agent_run(summary, no_data_in_events=bool(NO_DATA.search(events)))
        attempts.append(
            {
                "run_id": result.run_id,
                "session_id": result.session_id,
                "stop_reason": result.stop_reason,
                "cost_cents": result.list_cost_cents,
            }
        )
        if not retryable(summary, out, events) or attempt == retries:
            break
        print(f"TIC {tic}: retrying after {result.stop_reason}", file=sys.stderr)
    total = sum(a["cost_cents"] for a in attempts)
    out = replace(out, cost_cents=total)
    return out, {"attempts": attempts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runtime.eval_agents")
    parser.add_argument("--set", default="v0.1", dest="set_id")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--pilot", action="store_true", help="5 development stars")
    which.add_argument("--split", choices=["dev", "holdout"])
    parser.add_argument("--budget-cents", type=int, default=200, help="per session")
    parser.add_argument("--cap-cents", type=int, required=True, help="spend cap of the milestone")
    parser.add_argument("--milestone", default="M4")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args(argv)
    root = evals_dir()
    labels = json.loads((root / "sets" / args.set_id / "set.json").read_text())
    stars = (
        pilot(labels["stars"])
        if args.pilot
        else [s for s in labels["stars"] if s["split"] == args.split]
    )
    try:
        commit = pinned_commit()
        director = resource("./contexts/direction/agent.md")
        environment = resource("./environment_eval.yaml")
    except RepoStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    ver = versions()
    key = version_key(set_hash=labels["set_hash"], **ver)
    index = Index(root / "results" / args.set_id / "agents.jsonl")
    todo = [s["tic_id"] for s in stars if s["tic_id"] not in index.done(key)]
    ledger = RUNS / "ledger.jsonl"
    print(
        f"agents: {len(todo)} of {len(stars)} stars to run; {args.milestone} spent "
        f"{spent_cents(ledger, args.milestone) / 100:.2f} of {args.cap_cents / 100:.2f} USD",
        file=sys.stderr,
    )
    base = RunConfig(
        agent_id=director.id,
        agent_version=director.version,
        environment_id=environment.id,
        repo_url=REPO_URL,
        commit=commit,
        runs_dir=RUNS,
        ledger=ledger,
        cap_cents=args.cap_cents,
        kind="eval-pilot" if args.pilot else f"eval-{args.split}",
        milestone=args.milestone,
    )
    budget = Budget(ledger, args.cap_cents, args.budget_cents, args.milestone)
    stopped = None
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(run_star, tic, base, budget, args.retries): tic for tic in todo}
        for future in as_completed(futures):
            tic = futures[future]
            try:
                out, info = future.result()
            except SpendCapError as exc:
                stopped = str(exc)
                print(f"TIC {tic}: not started: {exc}", file=sys.stderr)
                continue
            index.add(key, out, commit=commit, versions=ver, agent_names=agent_names(), **info)
            print(
                f"TIC {tic}: {out.status} {out.final or ''} {out.cost_cents / 100:.2f} USD "
                f"flags={out.flags}",
                file=sys.stderr,
            )
    print(
        json.dumps(
            {
                "key": key,
                "index": str(index.path),
                "stopped_by_cap": stopped,
                "spent_usd": spent_cents(ledger, args.milestone) / 100,
            }
        )
    )
    return 1 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
