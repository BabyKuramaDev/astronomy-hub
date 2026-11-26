"""List every hub tool with its exact command line, from the CLI parsers themselves.

bin/hub --help        (or bin/hub with no arguments)
"""

import argparse
import importlib

CONTEXTS = (
    "acquisition",
    "preparation",
    "detection",
    "modeling",
    "catalog",
    "vetting",
    "review",
    "followup",
    "reporting",
    "direction",
)
COMMON = {"-h", "--tic", "--workspace", "--mission"}


def _option(action: argparse.Action) -> str:
    flag = max(action.option_strings, key=len)
    if action.nargs == 0:
        text = flag
    elif action.choices:
        text = f"{flag} {{{'|'.join(map(str, action.choices))}}}"
    else:
        text = f"{flag} <{flag.lstrip('-').replace('-', '_')}>"
    return text if action.required else f"[{text}]"


def tools() -> dict[str, list[tuple[str, str, str]]]:
    """context -> [(tool, help, usage line)]"""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for context in CONTEXTS:
        cli = importlib.import_module(f"contexts.{context}.cli").cli
        rows = []
        for name, parser in cli._subparsers.choices.items():
            options = []
            for action in parser._actions:
                if not action.option_strings or COMMON & set(action.option_strings):
                    continue
                options.append(_option(action))
            for group in parser._mutually_exclusive_groups:
                names = [max(a.option_strings, key=len) for a in group._group_actions]
                options = [o for o in options if not any(n in o for n in names)]
                options.insert(
                    0, "(" + " | ".join(_option(a).strip("[]") for a in group._group_actions) + ")"
                )
            usage = " ".join([f"bin/hub {context} {name} --tic <TIC>", *options])
            rows.append((name, parser.description or "", usage))
        out[context] = rows
    return out


def main() -> int:
    print("Run from /workspace/astronomy-hub: bin/hub <context> <tool> --tic <TIC> [options]")
    print("Each tool prints a JSON summary; exit 0 ok, 2 invalid input, 3 data not available.\n")
    for context, rows in tools().items():
        print(context)
        for name, help_text, usage in rows:
            print(f"  {name}: {help_text}")
            print(f"    {usage}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
