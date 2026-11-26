"""Tools of the `reporting` context: render-report."""

import argparse

from contexts.reporting.application.render_report import RenderReport
from contexts.reporting.infrastructure.jinja import JinjaRenderer
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def render_report(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    use_case = RenderReport(ctx.dossier, ctx.meta, JinjaRenderer())
    return ToolResult(summary=use_case.execute(args.summary))


cli = ToolCli(Context.REPORTING)
r = cli.tool(
    "render-report",
    "Write report.md from the dossier with a fixed template: verdict first, every number "
    "with the file it came from.",
    render_report,
)
r.add_argument("--summary", help="the Writer's prose, placed after the verdict")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
