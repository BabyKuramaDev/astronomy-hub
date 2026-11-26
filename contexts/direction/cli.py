"""Tools of the `direction` context: decide."""

import argparse

from contexts.direction.application.decide import Decide
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def decide(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    summary = Decide(ctx.dossier, ctx.meta, ctx.mission.direction).execute(args.mode, args.reason)
    return ToolResult(summary=summary, reason=args.reason)


cli = ToolCli(Context.DIRECTION)
d = cli.tool(
    "decide",
    "Compute the final verdict with the Director's rule from signal.json, catalog.json "
    "(explore mode only), vetting.json and review.json; write decision.json.",
    decide,
)
d.add_argument("--mode", choices=["explore", "eval"], required=True, help="run mode")
d.add_argument("--reason", required=True, help="the Director's justification")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
