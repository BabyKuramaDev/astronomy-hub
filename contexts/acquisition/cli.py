"""Tools of the `acquisition` context: fetch-lightcurves, fetch-star."""

import argparse

from contexts.acquisition.application.fetch_lightcurves import FetchLightcurves
from contexts.acquisition.application.fetch_star import FetchStar
from contexts.acquisition.infrastructure.mast import MastLightcurveArchive, MastTicCatalog
from contexts.acquisition.infrastructure.spoc_fits import SpocFitsReader
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def fetch_lightcurves(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    use_case = FetchLightcurves(
        MastLightcurveArchive(), SpocFitsReader(), ctx.dossier, ctx.meta, ctx.mission.acquisition
    )
    return ToolResult(summary=use_case.execute())


def fetch_star(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    use_case = FetchStar(MastTicCatalog(), ctx.dossier, ctx.meta, ctx.mission.acquisition)
    return ToolResult(summary=use_case.execute())


cli = ToolCli(Context.ACQUISITION)
cli.tool(
    "fetch-lightcurves",
    "Download SPOC 2-minute light curves of the selected sectors and extract PDCSAP_FLUX.",
    fetch_lightcurves,
)
cli.tool("fetch-star", "Fetch TIC parameters of the star and its neighbors.", fetch_star)
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
