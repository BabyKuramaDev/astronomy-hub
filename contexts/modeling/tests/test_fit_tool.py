import json
from pathlib import Path

import pytest

from contexts.modeling.cli import main
from contexts.modeling.tests.conftest import TIC, write_dossier
from shared.contracts import LogEntry, ModelFile
from shared.toolkit.dossier import Dossier

SHORT = ["--walkers", "16", "--steps", "60", "--burn", "20"]


def run(workspace: Path, *extra: str) -> int:
    return main(["fit-transit", "--tic", str(TIC), "--workspace", str(workspace), *SHORT, *extra])


def dossier(workspace: Path, **kwargs: str | bool) -> Path:
    root = workspace / "exoplanets" / str(TIC)
    write_dossier(root, **kwargs)  # type: ignore[arg-type]
    return root


def test_fit_with_stellar_radius(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = dossier(tmp_path)
    assert run(tmp_path) == 0
    summary = json.loads(capsys.readouterr().out)
    model = Dossier(root).read_envelope("model.json", ModelFile)
    assert model.data.planet_radius_rearth is not None
    assert model.data.stellar_source == "test TIC"
    assert set(model.inputs) == {"signal.json", "lightcurve_clean.parquet", "star.json"}
    assert set(summary["convergence"]) == {
        "converged",
        "tau_max",
        "n_post_burn",
        "autocorr_factor",
        "acceptance_mean",
        "acceptance_min",
    }
    assert summary["chain"] == {"walkers": 16, "steps": 60, "burn": 20, "seed": 42}
    assert any("not converged" in w for w in summary["warnings"])


@pytest.mark.parametrize(
    ("star", "message"),
    [("without_radius", "no stellar radius"), ("missing", "star.json not found")],
)
def test_fit_without_stellar_radius_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], star: str, message: str
) -> None:
    root = dossier(tmp_path, star=star)
    assert run(tmp_path) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["planet_radius_rearth"] is None
    assert any(message in w for w in summary["warnings"])
    model = Dossier(root).read_envelope("model.json", ModelFile)
    assert model.data.planet_radius_rearth is None
    assert model.data.stellar_source is None


def test_fit_without_detection_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dossier(tmp_path, detected=False)
    assert run(tmp_path) == 2
    assert "detected=false" in capsys.readouterr().err


def test_fit_is_reproducible(tmp_path: Path) -> None:
    root = dossier(tmp_path)
    assert run(tmp_path) == 0
    assert run(tmp_path) == 0
    lines = (root / "log.jsonl").read_text().splitlines()
    first, second = (LogEntry.model_validate_json(x) for x in lines)
    assert first.outputs == second.outputs
