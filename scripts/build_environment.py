"""Generate environment.yaml (the Managed Agents environment) from uv.lock.

The sandbox probe (M3) found python3 3.11 by default, so the environment installs no
pip packages: bin/setup-sandbox builds .venv with Python 3.12 from uv.lock (`uv sync
--frozen`, about 8 s). The pins below are still derived from the lock and listed as a
comment, so the file changes whenever the lock does.

    uv run python -m scripts.build_environment          # write environment.yaml
    uv run python -m scripts.build_environment --check  # exit 1 if it is out of date

The pip packages are the project's runtime dependencies and everything they pull in,
pinned with == to the versions in uv.lock, for Linux x86_64 and Python 3.12 (the
sandbox). Development and runtime (local client) groups are left out. The hosts are
the ones the tools reach; see docs/SPEC.md, Entorno.
"""

import argparse
import sys
import tomllib
from pathlib import Path

from packaging.markers import Marker
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "uv.lock"
OUTPUT = REPO / "environment.yaml"
NAME = "astronomy-hub"
# Sandbox platform for marker evaluation (Ubuntu 24.04, x86_64, Python 3.12).
SANDBOX = {
    "python_version": "3.12",
    "python_full_version": "3.12.0",
    "sys_platform": "linux",
    "platform_system": "Linux",
    "platform_machine": "x86_64",
    "os_name": "posix",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
    "extra": "",
}
ALLOWED_HOSTS = (
    "mast.stsci.edu",  # MAST queries and TIC
    "stpubdata.s3.us-east-1.amazonaws.com",  # MAST redirects TESS downloads here
    "exoplanetarchive.ipac.caltech.edu",  # crossmatch: pscomppars and TOI tables
    "exofop.ipac.caltech.edu",  # crossmatch: CTOIs
    "arxiv.org",  # Librarian's literature search
    "ui.adsabs.harvard.edu",
)


def runtime_pins(lock: dict) -> list[str]:
    packages = {canonicalize_name(p["name"]): p for p in lock["package"]}
    root = packages[canonicalize_name(NAME)]
    seen: set[str] = set()
    stack = [d for d in root.get("dependencies", [])]
    while stack:
        dep = stack.pop()
        marker = dep.get("marker")
        if marker and not Marker(marker).evaluate(SANDBOX):
            continue
        name = canonicalize_name(dep["name"])
        if name in seen:
            continue
        seen.add(name)
        stack.extend(packages[name].get("dependencies", []))
    return sorted(f"{packages[n]['name']}=={packages[n]['version']}" for n in seen)


def render(lock: dict) -> str:
    lines = [
        "# Managed Agents environment. Generated from uv.lock by scripts/build_environment.py;",
        "# do not edit by hand (a test checks it). Synced with ant apply.",
        "# No packages: the default python3 is 3.11, so bin/setup-sandbox runs",
        "# `uv sync --frozen --no-default-groups --python 3.12`, which installs:",
        *(f"#   {pin}" for pin in runtime_pins(lock)),
        f"name: {NAME}",
        "config:",
        "  type: cloud",
        "  packages:  # explicitly empty: an omitted field would keep the old packages",
        "    pip: []",
        "  networking:",
        "    type: limited",
        "    allow_package_managers: true  # uv sync reaches PyPI; also opens GitHub",
        "    allow_mcp_servers: false",
        "    allowed_hosts:",
        *(f"      - {host}" for host in ALLOWED_HOSTS),
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.build_environment")
    parser.add_argument("--check", action="store_true", help="fail if environment.yaml is stale")
    args = parser.parse_args(argv)
    text = render(tomllib.loads(LOCK.read_text()))
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != text:
            print("environment.yaml is out of date: run python -m scripts.build_environment",
                  file=sys.stderr)  # fmt: skip
            return 1
        return 0
    OUTPUT.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
