"""Tools of the `modeling` context: fit-transit."""

import argparse

from contexts.modeling.application.fit_transit import FitOverrides, FitTransit
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def fit_transit(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    overrides = FitOverrides(args.walkers, args.steps, args.burn, args.seed)
    use_case = FitTransit(ctx.dossier, ctx.meta, ctx.mission.modeling)
    return ToolResult(summary=use_case.execute(args.mode, overrides))


cli = ToolCli(Context.MODELING)
fit = cli.tool(
    "fit-transit",
    "Fit a transit model with jitter to the signal in signal.json and write model.json. "
    "quick (default) is least squares; mcmc (emcee) only runs on vetting candidates.",
    fit_transit,
)
fit.add_argument("--mode", choices=["quick", "mcmc"], default="quick", help="fit method")
fit.add_argument("--walkers", type=int, help="mcmc: override mission.yaml modeling.mcmc.walkers")
fit.add_argument("--steps", type=int, help="mcmc: override mission.yaml modeling.mcmc.steps")
fit.add_argument("--burn", type=int, help="mcmc: override mission.yaml modeling.mcmc.burn")
fit.add_argument("--seed", type=int, help="override mission.yaml modeling.seed")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
