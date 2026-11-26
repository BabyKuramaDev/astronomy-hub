"""Common CLI for every tool.

`python -m contexts.<context>.cli <tool> --tic <id> [--workspace DIR] [--mission NAME] ...`

The wrapper parses arguments, isolates caches inside the dossier, calls the
handler, prints a short JSON summary on stdout, writes errors to stderr on one
line, maps errors to exit codes (0 ok, 2 invalid input, 3 data not available)
and appends a line to log.jsonl.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from shared.contracts import LogEntry
from shared.kernel.contexts import Context
from shared.mission import MissionConfig, MissionError, load_mission
from shared.toolkit.caches import isolated_caches
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import ToolError
from shared.toolkit.meta import ToolMeta, utc_now
from shared.toolkit.version import hub_version


class ToolParser(argparse.ArgumentParser):
    """argparse with one-line errors on stderr and exit code 2."""

    def error(self, message: str) -> NoReturn:
        self.exit(2, f"error: {message}\n")


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be positive: {value}")
    return value


@dataclass(frozen=True)
class ToolContext:
    tic_id: int
    mission_name: str
    mission: MissionConfig
    dossier: Dossier
    meta: ToolMeta


@dataclass
class ToolResult:
    summary: dict[str, Any]
    reason: str | None = None
    extra_outputs: dict[str, str] = field(default_factory=dict)


Handler = Callable[[argparse.Namespace, ToolContext], ToolResult]


@dataclass
class ToolCli:
    context: Context
    parser: ToolParser = field(init=False)
    handlers: dict[str, Handler] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.parser = ToolParser(prog=f"python -m contexts.{self.context}.cli")
        self._subparsers = self.parser.add_subparsers(
            dest="tool", metavar="tool", required=True, parser_class=ToolParser
        )

    def tool(self, name: str, help_text: str, handler: Handler) -> argparse.ArgumentParser:
        sub = self._subparsers.add_parser(name, help=help_text, description=help_text)
        sub.add_argument("--tic", type=_positive_int, required=True, help="TIC id of the star")
        sub.add_argument("--workspace", type=Path, default=Path("workspace"), help="workspace root")
        sub.add_argument("--mission", default="exoplanets", help="mission name")
        self.handlers[name] = handler
        return sub

    def main(self, argv: Sequence[str] | None = None) -> int:
        argv = list(sys.argv[1:] if argv is None else argv)
        args = self.parser.parse_args(argv)
        try:
            mission = load_mission(args.mission)
        except MissionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        dossier = Dossier.for_target(args.workspace, args.mission, args.tic)
        meta = ToolMeta(
            context=self.context,
            tool=args.tool,
            tic_id=args.tic,
            mission=args.mission,
            version=hub_version(),
        )
        ctx = ToolContext(args.tic, args.mission, mission, dossier, meta)
        return run_handler(self.handlers[args.tool], args, ctx, argv)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def run_handler(
    handler: Handler, args: argparse.Namespace, ctx: ToolContext, argv: list[str]
) -> int:
    started = time.monotonic()
    ts = utc_now()
    result: ToolResult | None = None
    error: str | None = None
    exit_code = 0
    try:
        with isolated_caches(ctx.dossier.cache_dir):
            result = handler(args, ctx)
    except ToolError as exc:
        error, exit_code = (
            str(exc).splitlines()[0] if str(exc) else type(exc).__name__,
            exc.exit_code,
        )
    except Exception as exc:  # unexpected: still logged, reported on one line
        error, exit_code = f"{type(exc).__name__}: {exc}".splitlines()[0], 1
    duration = time.monotonic() - started

    if result is not None:
        print(json.dumps(result.summary, sort_keys=True, allow_nan=False))
    else:
        print(f"error: {error}", file=sys.stderr)

    entry = LogEntry(
        ts=ts,
        context=ctx.meta.context,
        tool=ctx.meta.tool,
        argv=argv,
        version=ctx.meta.version,
        duration_s=round(duration, 3),
        exit_code=exit_code,
        outputs=dict(sorted(ctx.dossier.writes.items())),
        summary=result.summary if result else None,
        reason=result.reason if result else None,
        error=error,
    )
    ctx.dossier.append_log(entry)
    return exit_code
