"""Tools of the `modeling` context: fit-transit."""

import argparse

from contexts.modeling.application.fit_transit import FitOverrides, FitTransit
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def fit_transit(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    overrides = FitOverrides(args.walkers, args.steps, args.burn, args.seed)
    use_case = FitTransit(ctx.dossier, ctx.meta, ctx.mission.modeling)
    return ToolResult(summary=use_case.execute(overrides))


cli = ToolCli(Context.MODELING)
fit = cli.tool(
    "fit-transit",
    "Fit a transit model (batman + emcee) to the signal in signal.json and write model.json.",
    fit_transit,
)
fit.add_argument("--walkers", type=int, help="override mission.yaml modeling.walkers")
fit.add_argument("--steps", type=int, help="override mission.yaml modeling.steps")
fit.add_argument("--burn", type=int, help="override mission.yaml modeling.burn")
fit.add_argument("--seed", type=int, help="override mission.yaml modeling.seed")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
