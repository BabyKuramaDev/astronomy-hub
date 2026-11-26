"""Shared pieces of the WASP-18 b end-to-end tests."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wasp18"
REPO = Path(__file__).resolve().parents[2]
SHORT_MCMC = ["--walkers", "20", "--steps", "300", "--burn", "100"]
START = "2026-12-01"


def reference() -> dict[str, Any]:
    return json.loads((FIXTURES / "reference.json").read_text())


def build_dossier(tic: int, workspace: Path, *extra: str) -> dict[str, Any]:
    """Run scripts/build_dossier.py as `make dossier` does, and return its summary."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.build_dossier", "--tic", str(tic),
         "--workspace", str(workspace), "--start", START, *extra, "--mcmc", *SHORT_MCMC],
        cwd=REPO, capture_output=True, text=True, check=False, timeout=3600,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
