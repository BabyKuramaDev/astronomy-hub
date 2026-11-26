import subprocess
import sys
from pathlib import Path

import pytest

from shared.kernel.contexts import Context

LAYERS = ("domain", "application", "infrastructure", "tests")


def test_context_enum_matches_context_directories(repo_root: Path) -> None:
    on_disk = {p.name for p in (repo_root / "contexts").iterdir() if (p / "__init__.py").exists()}
    assert on_disk == {c.value for c in Context}


@pytest.mark.parametrize("context", list(Context), ids=str)
def test_context_has_standard_layout(repo_root: Path, context: Context) -> None:
    base = repo_root / "contexts" / context
    for layer in LAYERS:
        assert (base / layer / "__init__.py").is_file(), f"missing {layer}/"
    assert (base / "cli.py").is_file()


@pytest.mark.parametrize("context", list(Context), ids=str)
def test_cli_without_tool_exits_with_invalid_input(repo_root: Path, context: Context) -> None:
    result = subprocess.run(
        [sys.executable, "-m", f"contexts.{context}.cli"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr


@pytest.mark.parametrize("context", list(Context), ids=str)
def test_cli_help_exits_cleanly(repo_root: Path, context: Context) -> None:
    result = subprocess.run(
        [sys.executable, "-m", f"contexts.{context}.cli", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert f"contexts.{context}.cli" in result.stdout
