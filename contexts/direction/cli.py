"""Tools of the `direction` context: decide."""

import argparse
from pathlib import Path

from contexts.direction.application.decide import Decide
from contexts.direction.application.package_dossier import PackageDossier
from contexts.direction.infrastructure.tarball import pack
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult


def decide(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    summary = Decide(ctx.dossier, ctx.meta, ctx.mission.direction).execute(args.mode, args.reason)
    return ToolResult(summary=summary, reason=args.reason)


def package_dossier(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    return ToolResult(summary=PackageDossier(ctx.dossier, ctx.meta, pack).execute(args.dest))


cli = ToolCli(Context.DIRECTION)
d = cli.tool(
    "decide",
    "Compute the final verdict with the Director's rule from signal.json, catalog.json "
    "(explore mode only), vetting.json and review.json; write decision.json.",
    decide,
)
d.add_argument("--mode", choices=["explore", "eval"], required=True, help="run mode")
d.add_argument("--reason", required=True, help="the Director's justification")
pkg = cli.tool(
    "package-dossier",
    "Validate every dossier JSON against its contract and write dossier-<tic>.tar.gz to "
    "--dest (the session outputs folder). The only tool that writes outside the dossier.",
    package_dossier,
)
pkg.add_argument("--dest", type=Path, default=Path("/mnt/session/outputs"), help="output folder")
main = cli.main

if __name__ == "__main__":
    raise SystemExit(main())
