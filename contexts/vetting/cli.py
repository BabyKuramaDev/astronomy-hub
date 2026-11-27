"""Tools of the `vetting` context: run-gates, run-gate, conclude."""

import argparse

from contexts.vetting.application.conclude import Conclude
from contexts.vetting.application.run_gates import RunGate, RunGates
from contexts.vetting.domain.gates import GATE_IDS
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def run_gates(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    use_case = RunGates(ctx.dossier, ctx.meta, ctx.mission.vetting, ctx.mission.detection.sde_min)
    return ToolResult(summary=use_case.execute())


def run_gate(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    use_case = RunGate(ctx.dossier, ctx.meta, ctx.mission.vetting, ctx.mission.detection.sde_min)
    return ToolResult(
        summary=use_case.execute(args.gate, args.duration_scale, args.window_durations)
    )


def conclude(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    summary = Conclude(ctx.dossier, ctx.meta).execute(args.rationale)
    return ToolResult(summary=summary, reason=args.rationale)


cli = ToolCli(Context.VETTING)
cli.tool(
    "run-gates",
    "Run the ten vetting gates once with the default parameters; write vetting/runs.json.",
    run_gates,
)
one = cli.tool(
    "run-gate",
    "Rerun one gate with other measurement parameters (thresholds never change); "
    "the run is added to vetting/runs.json.",
    run_gate,
)
one.add_argument("--gate", required=True, help=f"gate id: {', '.join(GATE_IDS)}")
one.add_argument("--duration-scale", type=float, help="multiply the transit duration")
one.add_argument("--window-durations", type=float, help="outer edge of the local baseline")
done = cli.tool(
    "conclude",
    "Combine the runs of every gate, compute the verdict with the rule and write vetting.json.",
    conclude,
)
done.add_argument("--rationale", required=True, help="one sentence per gate that matters")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
