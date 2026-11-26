"""Shared pieces of the WASP-18 b end-to-end tests."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wasp18"
REPO = Path(__file__).resolve().parents[2]
SHORT_CHAIN = ["--walkers", "16", "--steps", "60", "--burn", "20"]


def reference() -> dict[str, Any]:
    return json.loads((FIXTURES / "reference.json").read_text())


def tool(context: str, name: str, tic: int, workspace: Path, *extra: str) -> dict[str, Any]:
    """Run a tool exactly as an agent would, and return its stdout summary."""
    result = subprocess.run(
        [sys.executable, "-m", f"contexts.{context}.cli", name, "--tic", str(tic),
         "--workspace", str(workspace), *extra],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )  # fmt: skip
    assert result.returncode == 0, f"{context} {name}: {result.stderr}"
    assert result.stderr == "", f"{context} {name} wrote to stderr: {result.stderr}"
    return json.loads(result.stdout)


def detection_chain(tic: int, workspace: Path) -> dict[str, Any]:
    """clean -> search-period -> select-peak p1 -> fold -> fit-transit; returns summaries."""
    out = {"clean": tool("preparation", "clean", tic, workspace)}
    out["search"] = tool("detection", "search-period", tic, workspace)
    out["select"] = tool(
        "detection", "select-peak", tic, workspace, "--peak", "p1",
        "--reason", "end-to-end test: highest-ranked peak",
    )  # fmt: skip
    out["fold"] = tool("detection", "fold", tic, workspace, "--peak", "p1")
    out["fit"] = tool("modeling", "fit-transit", tic, workspace, *SHORT_CHAIN)
    return out
