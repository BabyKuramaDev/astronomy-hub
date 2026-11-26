"""Measure the Managed Agents sandbox once: python3, setup time, bash time limit.

uv run python -m runtime.probe [--budget-cents 50]
"""

import argparse
import json
import sys

from runtime.checks import tool_output
from runtime.ledger import SpendCapError
from runtime.managed import ManagedAgentsRuntime, RunConfig
from runtime.repo import REPO, REPO_URL, RepoStateError, pinned_commit, resource

COMMANDS = [
    "python3 --version; which python3 python3.12 uv; uv --version",
    "cd /workspace/astronomy-hub && git log -1 --format=%H",
    "cd /workspace/astronomy-hub && time bin/setup-sandbox",
    "cd /workspace/astronomy-hub && bin/hub detection search-period --help | head -3",
    "start=$(date +%s); sleep 330; echo slept $(( $(date +%s) - start ))",
    "start=$(date +%s); sleep 960; echo slept $(( $(date +%s) - start ))",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runtime.probe")
    parser.add_argument("--budget-cents", type=int, default=50)
    parser.add_argument("--cap-cents", type=int, default=2000)
    args = parser.parse_args(argv)
    try:
        commit = pinned_commit()
        agent = resource("./runtime/probe/agent.md")
        env = resource("./runtime/probe/environment.yaml")
    except RepoStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from runtime.platform import ManagedAgentsPlatform

    config = RunConfig(
        agent_id=agent.id,
        agent_version=agent.version,
        environment_id=env.id,
        repo_url=REPO_URL,
        commit=commit,
        runs_dir=REPO / "runs",
        ledger=REPO / "runs" / "ledger.jsonl",
        cap_cents=args.cap_cents,
        kind="probe",
        deadline_s=2400.0,
        output_retries=1,
    )
    config.message = "Run these commands, one bash call each, in this order:\n" + "\n".join(
        f"{i}. {c}" for i, c in enumerate(COMMANDS, 1)
    )
    runtime = ManagedAgentsRuntime(ManagedAgentsPlatform(), config)
    reference = json.loads((REPO / "tests" / "fixtures" / "wasp18" / "reference.json").read_text())
    try:
        result = runtime.run(reference["tic_id"], "exoplanets", "explore", args.budget_cents)
    except SpendCapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    records = [
        json.loads(x)
        for x in (result.summary_file.parent / "events.jsonl").read_text().splitlines()
    ]
    report = {c: tool_output(records, c.split(";")[0][:40]) for c in COMMANDS}
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "list_cost_usd": result.list_cost_cents / 100,
                "wall_seconds": result.wall_seconds,
                "outputs": report,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
