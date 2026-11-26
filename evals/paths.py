"""Where the eval sets and per-star results live: outside the repository mounted in
the sandbox. HUB_EVALS_DIR overrides the default ~/Code/astronomy-hub-evals (a local
folder with its own git, never pushed)."""

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def evals_dir() -> Path:
    return Path(os.environ.get("HUB_EVALS_DIR", REPO.parent / "astronomy-hub-evals"))
