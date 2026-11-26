"""Tools of the `catalog` context: crossmatch."""

import argparse

from contexts.catalog.application.add_literature import AddLiterature
from contexts.catalog.application.crossmatch import Crossmatch
from contexts.catalog.infrastructure.archive import ArchiveCatalogs
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult
from shared.toolkit.retry import RetryPolicy


def crossmatch(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    cfg = ctx.mission.catalog
    catalogs = ArchiveCatalogs(RetryPolicy(cfg.retry.attempts, cfg.retry.backoff_s))
    return ToolResult(summary=Crossmatch(catalogs, ctx.dossier, ctx.meta, cfg).execute())


def add_literature(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    summary = AddLiterature(ctx.dossier, ctx.meta).execute(args.title, args.url, args.note)
    return ToolResult(summary=summary)


cli = ToolCli(Context.CATALOG)
cli.tool(
    "crossmatch",
    "Look the TIC up in pscomppars, the TOI list and the CTOIs; mark which entries match "
    "the period of signal.json (aliases included) and write catalog.json.",
    crossmatch,
)
lit = cli.tool(
    "add-literature",
    "Record a literature source in catalog.json (title, URL, what it says about this object).",
    add_literature,
)
lit.add_argument("--title", required=True, help="title of the paper or page")
lit.add_argument("--url", required=True, help="http(s) URL of the source")
lit.add_argument("--note", default="", help="what the source says about this star or signal")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
