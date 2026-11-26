"""Tools of the `followup` context: ephemeris."""

import argparse
from datetime import UTC, datetime

from contexts.followup.application.ephemeris import Ephemeris
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def _start(text: str) -> datetime:
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an ISO date or time: {text!r}") from None
    if moment.tzinfo is None:  # a bare date or time is taken as UTC
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def ephemeris(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    start = args.start or datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return ToolResult(summary=Ephemeris(ctx.dossier, ctx.meta, ctx.mission.followup).execute(start))


cli = ToolCli(Context.FOLLOWUP)
eph = cli.tool(
    "ephemeris",
    "Predict the next transits from model.json, with their timing uncertainty; "
    "write ephemeris.json.",
    ephemeris,
)
eph.add_argument(
    "--start",
    type=_start,
    help="first moment to list, ISO 8601 (UTC if no zone); default: today 00:00 UTC",
)
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
