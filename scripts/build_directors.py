"""Render both Director agents from contexts/direction/director.yaml.

    uv run python -m scripts.build_directors [--check]

agent.md directs explore and full runs; agent_eval.md directs eval (blind) runs with a
roster of three. Both share every line except the roster and the steps; the common
rules come from shared/prompts/common.md, like every other agent.
"""

import argparse
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
DIRECTION = REPO / "contexts" / "direction"
SOURCE = DIRECTION / "director.yaml"
COMMON = REPO / "shared" / "prompts" / "common.md"


def render_all() -> dict[Path, str]:
    source = yaml.safe_load(SOURCE.read_text())
    common = COMMON.read_text().strip()
    out = {}
    for filename, variant in source["variants"].items():
        roster = "\n".join(f"      - ../{c}/agent.md" for c in variant["roster"])
        front = source["frontmatter"].replace("@ROSTER@", roster)
        body = source["body"].replace("@STEPS@", variant["steps"].strip()).rstrip()
        out[DIRECTION / filename] = f"---\n{front}---\n\n{body}\n\n{common}\n"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.build_directors")
    parser.add_argument("--check", action="store_true", help="fail if a Director file is stale")
    args = parser.parse_args(argv)
    for path, text in render_all().items():
        if args.check:
            if not path.exists() or path.read_text() != text:
                print(
                    f"{path.name} is out of date: run python -m scripts.build_directors",
                    file=sys.stderr,
                )
                return 1
        else:
            path.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
