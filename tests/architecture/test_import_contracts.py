"""import-linter contracts: they pass on the repo and break on each kind of violation."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

LINT_IMPORTS = str(Path(sys.executable).with_name("lint-imports"))
COPIED = ("contexts", "shared", "evals", "runtime")


def lint_imports(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [LINT_IMPORTS, "--no-cache"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo_copy(repo_root: Path, tmp_path: Path) -> Path:
    for name in COPIED:
        shutil.copytree(
            repo_root / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copy(repo_root / "pyproject.toml", tmp_path / "pyproject.toml")
    return tmp_path


def test_repo_keeps_every_import_contract(repo_root: Path) -> None:
    result = lint_imports(repo_root)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("module", "source", "broken_contract"),
    [
        pytest.param(
            "contexts/detection/domain/leak.py",
            "import contexts.catalog.domain\n",
            "Contexts are independent of each other",
            id="context-imports-another-context",
        ),
        pytest.param(
            "contexts/review/tests/test_leak.py",
            "from contexts.detection import cli\n",
            "Contexts are independent of each other",
            id="context-tests-import-another-context",
        ),
        pytest.param(
            "shared/kernel/leak.py",
            "from contexts.vetting import domain\n",
            "shared does not import contexts",
            id="shared-imports-context",
        ),
        pytest.param(
            "contexts/vetting/domain/leak.py",
            "from contexts.vetting import infrastructure\n",
            "Layers inside each context",
            id="domain-imports-infrastructure",
        ),
        pytest.param(
            "contexts/modeling/application/leak.py",
            "from contexts.modeling import cli\n",
            "Layers inside each context",
            id="application-imports-cli",
        ),
        pytest.param(
            "contexts/reporting/application/leak.py",
            "import anthropic\n",
            "Only runtime imports anthropic",
            id="context-imports-anthropic",
        ),
        pytest.param(
            "shared/contracts/leak.py",
            "from anthropic import Anthropic\n",
            "Only runtime imports anthropic",
            id="shared-imports-anthropic",
        ),
        pytest.param(
            "evals/leak.py",
            "import contexts.direction\n",
            "evals does not import contexts",
            id="evals-imports-context",
        ),
    ],
)
def test_violation_breaks_contract(
    repo_copy: Path, module: str, source: str, broken_contract: str
) -> None:
    (repo_copy / module).write_text(source, encoding="utf-8")
    result = lint_imports(repo_copy)
    assert result.returncode != 0
    broken = [line for line in result.stdout.splitlines() if line.endswith("BROKEN")]
    assert any(line.startswith(broken_contract) for line in broken), result.stdout


@pytest.mark.parametrize(
    ("module", "source"),
    [
        pytest.param("runtime/client.py", "import anthropic\n", id="runtime-imports-anthropic"),
        pytest.param(
            "contexts/vetting/cli.py",
            "from contexts.vetting import infrastructure\nfrom shared import contracts\n",
            id="cli-imports-lower-layer-and-shared",
        ),
        pytest.param(
            "evals/scorer.py", "from shared import contracts\n", id="evals-imports-shared"
        ),
    ],
)
def test_allowed_imports_keep_contracts(repo_copy: Path, module: str, source: str) -> None:
    (repo_copy / module).write_text(source, encoding="utf-8")
    result = lint_imports(repo_copy)
    assert result.returncode == 0, result.stdout
