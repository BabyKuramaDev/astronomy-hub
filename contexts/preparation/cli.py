"""Tools of the `preparation` context: clean."""

import argparse

from contexts.preparation.application.clean import Clean
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def clean(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    return ToolResult(summary=Clean(ctx.dossier, ctx.meta, ctx.mission.preparation).execute())


cli = ToolCli(Context.PREPARATION)
cli.tool(
    "clean",
    "Normalize per sector, detrend, clip upward outliers and stitch sectors.",
    clean,
)
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
