"""make hello: run WASP-18 b on Managed Agents and check the M3 acceptance criterion.

    uv run python -m runtime.hello [--mode eval|full|explore] [--budget-cents N] [--cap-cents N]

eval: the eval profile (Director, Searcher, Devil's Advocate, Reviewer) ends at decide
with a valid dossier, final candidate and the period within 1 percent of the catalog.
full: the same, then the Librarian and the Writer: all six agents work (smoke test).
explore: Catalog cuts early as known.
"""

import argparse
import json
import sys

from runtime.checks import EVAL_AGENTS, acceptance, agent_names, setup_report
from runtime.ledger import SpendCapError
from runtime.managed import ManagedAgentsRuntime, RunConfig
from runtime.repo import REPO, REPO_URL, RepoStateError, pinned_commit, resource

REFERENCE = REPO / "tests" / "fixtures" / "wasp18" / "reference.json"
RUNS = REPO / "runs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runtime.hello")
    parser.add_argument("--mode", choices=["eval", "full", "explore"], default="eval")
    parser.add_argument("--budget-cents", type=int, default=500)
    parser.add_argument("--cap-cents", type=int, default=1000, help="total spend cap for M4")
    args = parser.parse_args(argv)
    reference = json.loads(REFERENCE.read_text())
    try:
        commit = pinned_commit()
        blind = args.mode == "eval"  # the eval Director has a roster of three
        director = resource(
            "./contexts/direction/agent_eval.md" if blind else "./contexts/direction/agent.md"
        )
        environment = resource("./environment_eval.yaml" if blind else "./environment.yaml")
    except RepoStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    from runtime.platform import ManagedAgentsPlatform

    config = RunConfig(
        agent_id=director.id,
        agent_version=director.version,
        environment_id=environment.id,
        repo_url=REPO_URL,
        commit=commit,
        runs_dir=RUNS,
        ledger=RUNS / "ledger.jsonl",
        cap_cents=args.cap_cents,
        kind=f"hello-{args.mode}",
    )
    try:
        result = ManagedAgentsRuntime(ManagedAgentsPlatform(), config).run(
            reference["tic_id"], "exoplanets", args.mode, args.budget_cents
        )
    except SpendCapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = json.loads(result.summary_file.read_text())
    records = [
        json.loads(x)
        for x in (result.summary_file.parent / "events.jsonl").read_text().splitlines()
    ]
    expected = "known" if args.mode == "explore" else "candidate"
    required = {"eval": list(EVAL_AGENTS), "full": agent_names(), "explore": None}[args.mode]
    summary["setup"] = setup_report(records)
    summary["acceptance"] = acceptance(
        summary, result.dossier, reference["period_days"], expected, required
    )
    result.summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "session_id": result.session_id,
                "stop_reason": result.stop_reason,
                "list_cost_usd": result.list_cost_cents / 100,
                "wall_seconds": result.wall_seconds,
                "acceptance": summary["acceptance"],
                "audit_flags": len(summary["audit"]["flags"]),
                "setup": summary["setup"],
                "summary": str(result.summary_file),
            },
            indent=2,
        )
    )
    return 0 if summary["acceptance"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
