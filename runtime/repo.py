"""Facts about the local checkout and the IDs that ant apply recorded."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "claude-lock.json"
REPO_URL = "https://github.com/BabyKuramaDev/astronomy-hub"


class RepoStateError(RuntimeError):
    """The checkout cannot be pinned for a session."""


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def pinned_commit(fetch: bool = True) -> str:
    """HEAD, if the tree is clean and HEAD is on origin/main (what the session clones)."""
    if _git("status", "--porcelain"):
        raise RepoStateError("the working tree has uncommitted changes: commit them first")
    if fetch:
        _git("fetch", "--quiet", "origin", "main")
    head = _git("rev-parse", "HEAD")
    merged = subprocess.run(
        ["git", "merge-base", "--is-ancestor", head, "origin/main"], cwd=REPO, check=False
    )
    if merged.returncode != 0:
        raise RepoStateError(f"HEAD {head[:9]} is not on origin/main: push it first")
    return head


@dataclass(frozen=True)
class Resource:
    id: str
    version: int | None


def resource(path: str, lock: Path = LOCK) -> Resource:
    """The ID of a file synced by ant apply, e.g. './contexts/direction/agent.md'."""
    if not lock.exists():
        raise RepoStateError("claude-lock.json not found: run ant apply first")
    resources = json.loads(lock.read_text()).get("resources", {})
    entry = resources.get(path) or resources.get(path.removeprefix("./"))
    if entry is None:
        raise RepoStateError(f"{path} is not in claude-lock.json: run ant apply")
    version = entry.get("version")
    return Resource(entry["id"], int(version) if version is not None else None)
