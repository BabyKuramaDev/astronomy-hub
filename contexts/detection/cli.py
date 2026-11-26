"""Tools of the `detection` context: search-period, select-peak, fold."""

import argparse

from contexts.detection.application.fold import Fold, FoldRequest
from contexts.detection.application.search_period import SearchPeriod
from contexts.detection.application.select_peak import SelectPeak
from contexts.detection.infrastructure.figures import render_fold
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def search_period(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    return ToolResult(summary=SearchPeriod(ctx.dossier, ctx.meta, ctx.mission.detection).execute())


def select_peak(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    use_case = SelectPeak(ctx.dossier, ctx.meta, ctx.mission.detection)
    summary = use_case.execute(None if args.no_signal else args.peak)
    return ToolResult(summary=summary, reason=args.reason)


def fold(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    use_case = Fold(ctx.dossier, ctx.meta, ctx.mission.detection.fold, render_fold)
    request = FoldRequest(args.peak, args.period, args.epoch, args.duration)
    return ToolResult(summary=use_case.execute(request))


cli = ToolCli(Context.DETECTION)
cli.tool(
    "search-period",
    "Run BLS on lightcurve_clean.parquet and write the best peaks to search.json.",
    search_period,
)
select = cli.tool(
    "select-peak",
    "Record the chosen peak (or no signal) in signal.json, from search.json.",
    select_peak,
)
choice = select.add_mutually_exclusive_group(required=True)
choice.add_argument("--peak", help="peak id from search.json, for example p1")
choice.add_argument("--no-signal", action="store_true", help="record that there is no signal")
select.add_argument("--reason", help="why this peak was chosen; stored in log.jsonl only")

fold_parser = cli.tool(
    "fold",
    "Fold the clean light curve on a peak or period; write data, figure and a numeric summary.",
    fold,
)
fold_parser.add_argument("--peak", help="take period, epoch and duration from this peak")
fold_parser.add_argument("--period", type=float, help="period in days")
fold_parser.add_argument("--epoch", type=float, help="mid-transit time in BTJD")
fold_parser.add_argument("--duration", type=float, help="transit duration in hours")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
