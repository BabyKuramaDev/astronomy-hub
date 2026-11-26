from pathlib import Path

import pytest

from shared.kernel.contexts import Context
from tests.architecture.domain_purity import find_violations


def pure_modules(root: Path) -> list[Path]:
    """Every domain module of every context, plus the shared kernel."""
    files = list((root / "contexts").glob("*/domain/**/*.py"))
    files += list((root / "shared" / "kernel").glob("**/*.py"))
    return sorted(files)


def test_scan_covers_every_context_domain(repo_root: Path) -> None:
    scanned = {p.relative_to(repo_root).parent for p in pure_modules(repo_root)}
    for context in Context:
        assert Path("contexts", context, "domain") in scanned
    assert Path("shared", "kernel") in scanned


def test_domain_code_does_no_io(repo_root: Path) -> None:
    violations = []
    for path in pure_modules(repo_root):
        rel = str(path.relative_to(repo_root))
        violations += find_violations(path.read_text(encoding="utf-8"), rel)
    assert violations == []


@pytest.mark.parametrize(
    "source",
    [
        "import os",
        "import os.path",
        "import sys as system",
        "from pathlib import Path",
        "from urllib.request import urlopen",
        "import astropy.io.fits",
        "from astropy.io import fits",
        "from astropy import io",
        "import lightkurve",
        "import importlib",
        "open('x')",
        "input()",
        "print('hi')",
        "__import__('os')",
        "def f():\n    print('nested')",
    ],
)
def test_checker_flags_io(source: str) -> None:
    assert find_violations(source)


@pytest.mark.parametrize(
    "source",
    [
        "import math",
        "import osmosis",
        "import astropy.units as u",
        "from astropy import constants",
        "from dataclasses import dataclass",
        "from . import model",
        "from .open import thing",
        "self.print_summary()",
        "x.open()",
    ],
)
def test_checker_allows_pure_code(source: str) -> None:
    assert find_violations(source) == []
