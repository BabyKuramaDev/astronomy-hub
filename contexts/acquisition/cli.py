"""Command-line entry point of the `acquisition` context.

Each use case is exposed as a tool (a subcommand). There are no tools yet, so
every invocation exits with status 2 (invalid input).
"""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m contexts.acquisition.cli")
    parser.add_subparsers(dest="tool", metavar="tool", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
