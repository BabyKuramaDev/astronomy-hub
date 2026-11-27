import json
from pathlib import Path

import pytest

from contexts.modeling.cli import main
from contexts.modeling.tests.conftest import TIC, write_dossier, write_vetting
from shared.contracts import LogEntry, ModelFile
from shared.toolkit.dossier import Dossier

SHORT = ["--walkers", "20", "--steps", "60", "--burn", "20"]


def run(workspace: Path, *extra: str) -> int:
    return main(["fit-transit", "--tic", str(TIC), "--workspace", str(workspace), *extra])


def dossier(workspace: Path, **kwargs: str | bool) -> Path:
    root = workspace / "exoplanets" / str(TIC)
    write_dossier(root, **kwargs)  # type: ignore[arg-type]
    return root


def test_quick_fit_is_the_default(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = dossier(tmp_path)
    assert run(tmp_path) == 0
    summary = json.loads(capsys.readouterr().out)
    model = Dossier(root).read_envelope("model.json", ModelFile)
    assert model.data.method == "quick" == summary["method"]
    assert model.data.convergence is None
    assert "convergence" not in summary
    assert model.data.planet_radius_rearth is not None
    assert model.data.stellar_source == "test TIC"
    assert model.data.duration_hours.value > 0
    assert set(model.inputs) == {"signal.json", "lightcurve_clean.parquet", "star.json"}


def test_mcmc_on_a_candidate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = dossier(tmp_path)
    write_vetting(root, "candidate")
    assert run(tmp_path, "--mode", "mcmc", *SHORT) == 0
    summary = json.loads(capsys.readouterr().out)
    model = Dossier(root).read_envelope("model.json", ModelFile)
    assert model.data.method == "mcmc"
    assert model.data.convergence is not None
    assert model.data.convergence.walkers == 20
    assert "vetting.json" in model.inputs
    assert set(summary["convergence"]) >= {"converged", "tau_max", "acceptance_mean"}
    assert any("not converged" in w for w in summary["warnings"])


@pytest.mark.parametrize(
    ("verdict", "message"),
    [(None, "needs vetting.json"), ("inconclusive", "only runs on candidates")],
)
def test_mcmc_refuses_non_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], verdict: str | None, message: str
) -> None:
    root = dossier(tmp_path)
    if verdict:
        write_vetting(root, verdict)
    assert run(tmp_path, "--mode", "mcmc", *SHORT) == 2
    assert message in capsys.readouterr().err


def test_mcmc_refuses_vetting_of_another_signal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = dossier(tmp_path)
    write_vetting(root, "candidate")
    signal = root / "signal.json"
    signal.write_text(signal.read_text().replace('"snr": 80.0', '"snr": 81.0'))
    assert run(tmp_path, "--mode", "mcmc", *SHORT) == 2
    assert "another signal.json" in capsys.readouterr().err


def test_chain_options_need_mcmc(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dossier(tmp_path)
    assert run(tmp_path, *SHORT) == 2
    assert "--mode mcmc" in capsys.readouterr().err


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


def test_a_failed_fit_is_a_result_not_a_crash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from contexts.modeling.application import fit_transit
    from contexts.modeling.domain.fit import FitError

    def no_samples(*_args: object, **_kwargs: object) -> None:
        raise FitError("no valid samples to summarize")

    monkeypatch.setattr(fit_transit, "fit_quick", no_samples)
    root = dossier(tmp_path)
    assert run(tmp_path) == 0
    summary = json.loads(capsys.readouterr().out)
    model = Dossier(root).read_envelope("model.json", ModelFile).data
    assert (model.status, model.failure) == ("failed", "no valid samples to summarize")
    assert summary["status"] == "failed"
    assert model.rp_rs is None
    assert model.duration_hours is None


def test_an_impossible_geometry_is_a_failed_fit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from contexts.modeling.application import fit_transit
    from shared.contracts.model import Measurement

    real = fit_transit.fit_quick

    def inside_the_star(*args: object, **kwargs: object) -> object:
        fit = real(*args, **kwargs)
        return replace(fit, a_rs=Measurement(value=0.8, err_lower=0.1, err_upper=0.1))

    monkeypatch.setattr(fit_transit, "fit_quick", inside_the_star)
    root = dossier(tmp_path)
    assert run(tmp_path) == 0
    model = Dossier(root).read_envelope("model.json", ModelFile).data
    assert model.status == "failed"
    assert "inside the star" in (model.failure or "")


def test_bad_chain_settings_are_still_input_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = dossier(tmp_path)
    write_vetting(root, "candidate")
    assert run(tmp_path, "--mode", "mcmc", "--walkers", "20", "--steps", "10", "--burn", "20") == 2
    assert not (root / "model.json").exists()
