"""Tools of the `review` context: reproduce, conclude."""

import argparse

from contexts.review.application.conclude import Conclude
from contexts.review.application.reproduce import Reproduce
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def reproduce(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    return ToolResult(summary=Reproduce(ctx.dossier, ctx.meta, ctx.mission.review).execute())


def conclude(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    summary = Conclude(ctx.dossier, ctx.meta, ctx.mission.review).execute(args.rationale)
    return ToolResult(summary=summary, reason=args.rationale)


cli = ToolCli(Context.REVIEW)
cli.tool(
    "reproduce",
    "Redo cleaning (running median) and search (TLS) from the raw per-sector tables, "
    "without reading signal.json; write review/reproduction.json.",
    reproduce,
)
done = cli.tool(
    "conclude",
    "Compare review/reproduction.json with signal.json by the rule and write review.json.",
    conclude,
)
done.add_argument("--rationale", required=True, help="why the result holds, in a sentence")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
