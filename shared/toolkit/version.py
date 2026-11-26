"""Tool version for produced_by.version: 0.1.0+g<sha>[.dirty], or 0.1.0 without git."""

import subprocess
from functools import cache
from pathlib import Path

HUB_VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def describe_version(sha: str | None, dirty: bool) -> str:
    if not sha:
        return HUB_VERSION
    return f"{HUB_VERSION}+g{sha}" + (".dirty" if dirty else "")


@cache
def hub_version(repo: Path = REPO_ROOT) -> str:
    sha = _git(repo, "rev-parse", "--short", "HEAD")
    status = _git(repo, "status", "--porcelain") if sha else None
    return describe_version(sha, dirty=bool(status))
