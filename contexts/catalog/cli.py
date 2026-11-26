"""Tools of the `catalog` context: crossmatch."""

import argparse

from contexts.catalog.application.crossmatch import Crossmatch
from contexts.catalog.infrastructure.archive import ArchiveCatalogs
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult
from shared.toolkit.retry import RetryPolicy


def crossmatch(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    cfg = ctx.mission.catalog
    catalogs = ArchiveCatalogs(RetryPolicy(cfg.retry.attempts, cfg.retry.backoff_s))
    return ToolResult(summary=Crossmatch(catalogs, ctx.dossier, ctx.meta, cfg).execute())


cli = ToolCli(Context.CATALOG)
cli.tool(
    "crossmatch",
    "Look the TIC up in pscomppars, the TOI list and the CTOIs; mark which entries match "
    "the period of signal.json (aliases included) and write catalog.json.",
    crossmatch,
)
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
