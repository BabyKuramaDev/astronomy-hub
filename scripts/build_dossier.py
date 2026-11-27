"""Build a star's complete dossier without an LLM, running every tool as an agent would.

    uv run python -m scripts.build_dossier [--tic ID] [--mode eval|full|explore]
                                           [--workspace DIR] [--from STAGE]

Each agent's choice is replaced by a fixed rule, so the run is deterministic:
- Searcher: the first peak of search.json that select-peak accepts, or --no-signal.
- Director (explore): stop after Catalog when catalog.json says the signal is known.
- Devil's advocate: run-gates and conclude, no reruns. A false_positive skips the MCMC
  and the review: that verdict decides on its own.
- Modeler: the MCMC only runs on a candidate in explore mode; eval metrics never use it.
- Reviewer: reproduce and conclude.
- Director: decide. eval mode (the eval profile) ends there: no Catalog, no report.
  full mode decides blind like eval, then runs Catalog and the report.
- Writer: ephemeris and render-report (explore and full).

Without --tic it uses WASP-18 b's TIC from tests/fixtures/wasp18/reference.json.
The tools are called with subprocess, exactly as an agent calls them with bash.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
WASP18_REFERENCE = REPO / "tests" / "fixtures" / "wasp18" / "reference.json"
STEPS = ("acquisition", "catalog")  # groups that --skip accepts (they need the network)
KNOWN = {"known_planet", "toi", "ctoi"}
KNOWN_FALSE = {"known_false_positive", "eclipsing_binary"}


class ToolFailedError(RuntimeError):
    pass


class Runner:
    def __init__(self, tic: int, workspace: Path, mission: str) -> None:
        self.tic, self.workspace, self.mission = tic, workspace, mission
        self.steps: list[dict[str, Any]] = []

    def tool(self, context: str, name: str, *extra: str, allow: tuple[int, ...] = ()) -> Any:
        argv = [
            sys.executable,
            "-m",
            f"contexts.{context}.cli",
            name,
            "--tic",
            str(self.tic),
            "--workspace",
            str(self.workspace),
            "--mission",
            self.mission,
            *extra,
        ]
        started = time.monotonic()
        result = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, check=False)
        self.steps.append(
            {
                "tool": f"{context} {name}",
                "exit": result.returncode,
                "seconds": round(time.monotonic() - started, 1),
            }
        )
        print(f"{context} {name}: exit {result.returncode}", file=sys.stderr)
        if result.returncode == 0:
            return json.loads(result.stdout)
        if result.returncode in allow:
            return None
        raise ToolFailedError(
            f"{context} {name} exited {result.returncode}: {result.stderr.strip()}"
        )


STAGES = ("start", "select", "fit", "vetting", "review")


def read_data(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text())["data"]


def build(args: argparse.Namespace) -> dict[str, Any]:
    """Run the pipeline from args.from_stage on; earlier stages are read from the dossier."""
    run = Runner(args.tic, args.workspace, args.mission)
    skip = set(args.skip)
    stage = STAGES.index(args.from_stage)
    root = args.workspace / args.mission / str(args.tic)
    if stage == 0:
        if "acquisition" not in skip:
            run.tool("acquisition", "fetch-lightcurves")
            run.tool("acquisition", "fetch-star")
        run.tool("preparation", "clean")
        run.tool("detection", "search-period")

    if stage <= 1:
        search = read_data(root, "search.json")
        chosen = None
        for peak in search["peaks"]:
            reason = (
                f"Scripted run: first peak accepted by select-peak ({peak['id']}, "
                f"SNR {peak['snr']})."
            )
            accepted = run.tool(
                "detection", "select-peak", "--peak", peak["id"], "--reason", reason, allow=(2,)
            )
            if accepted is not None:
                chosen = peak["id"]
                break
        if chosen is None:
            run.tool(
                "detection",
                "select-peak",
                "--no-signal",
                "--reason",
                "Scripted run: select-peak accepts no peak.",
            )
            return finish(run, args, catalog_done=False)
        run.tool("detection", "fold", "--peak", chosen)
    elif not read_data(root, "signal.json")["detected"]:
        return finish(run, args, catalog_done=False)

    if stage <= 2:
        run.tool("modeling", "fit-transit")
    catalog_done = args.mode == "explore" and "catalog" not in skip and stage <= 2
    if catalog_done:
        catalog = run.tool("catalog", "crossmatch")
        if catalog["status"] in KNOWN | KNOWN_FALSE:
            return finish(run, args, catalog_done=True)

    if stage <= 3:
        gates = run.tool("vetting", "run-gates")
        failing = [
            g["gate"] for g in gates["gates"] if g["status"] != "pass" and g["severity"] != "info"
        ]
        vetting = run.tool(
            "vetting",
            "conclude",
            "--rationale",
            "Scripted run without reruns: "
            + (f"gates not passing: {', '.join(failing)}." if failing else "every gate passes."),
        )
    else:
        vetting = read_data(root, "vetting.json")
    if vetting["verdict"] != "false_positive":  # a false positive needs no MCMC nor review
        if vetting["verdict"] == "candidate" and args.mode == "explore":
            run.tool("modeling", "fit-transit", "--mode", "mcmc", *args.mcmc)
        run.tool("review", "reproduce")
        run.tool(
            "review",
            "conclude",
            "--rationale",
            "Scripted run: the rule compares period and depth with signal.json.",
        )
    return finish(run, args, catalog_done=catalog_done)


def finish(run: Runner, args: argparse.Namespace, catalog_done: bool) -> dict[str, Any]:
    decision = run.tool(
        "direction",
        "decide",
        "--mode",
        "explore" if args.mode == "explore" else "eval",
        "--reason",
        "Scripted run: final verdict from the Director's rule.",
    )
    root = args.workspace / args.mission / str(args.tic)
    if args.mode == "eval":  # the eval profile ends at decide
        return summary_of(run, args, decision, root)
    if args.mode == "full" and "catalog" not in args.skip and not catalog_done:
        run.tool("catalog", "crossmatch")  # blind: after the decision
    if (root / "model.json").exists() and decision["final"] in ("candidate", "inconclusive"):
        run.tool("followup", "ephemeris", *(["--start", args.start] if args.start else []))
    run.tool("reporting", "render-report")
    return summary_of(run, args, decision, root)


def summary_of(run: Runner, args: argparse.Namespace, decision: Any, root: Path) -> dict[str, Any]:
    return {
        "tic_id": args.tic,
        "mode": args.mode,
        "final": decision["final"],
        "basis": decision["basis"],
        "steps": run.steps,
        "dossier": str(root),
    }


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_dossier",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--tic", type=int, help="TIC id (default: WASP-18 b from the fixtures)")
    parser.add_argument("--mode", choices=["eval", "full", "explore"], default="eval")
    parser.add_argument("--workspace", type=Path, default=Path("workspace"))
    parser.add_argument("--mission", default="exoplanets")
    parser.add_argument(
        "--skip",
        type=lambda s: [x for x in s.split(",") if x],
        default=[],
        help=f"comma-separated groups whose files are already there: {STEPS}",
    )
    parser.add_argument(
        "--mcmc",
        nargs=argparse.REMAINDER,
        default=[],
        help="extra fit-transit options for the MCMC, e.g. --steps 400 --burn 100",
    )
    parser.add_argument("--start", help="ephemeris --start (default: today 00:00 UTC)")
    parser.add_argument(
        "--from",
        dest="from_stage",
        choices=STAGES,
        default="start",
        help="rerun from this stage, reading the earlier ones from the dossier",
    )
    args = parser.parse_args(argv)
    unknown = set(args.skip) - set(STEPS)
    if unknown:
        parser.error(f"unknown --skip groups: {sorted(unknown)}")
    if args.tic is None:
        args.tic = int(json.loads(WASP18_REFERENCE.read_text())["tic_id"])
    args.workspace = args.workspace.resolve()
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    try:
        summary = build(args)
    except ToolFailedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
