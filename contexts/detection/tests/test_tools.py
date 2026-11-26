"""The three detection tools through their CLI, on a synthetic clean light curve."""

import json
from pathlib import Path

import pytest

from contexts.detection.cli import main
from shared.contracts import FoldFile, LogEntry, SearchFile, SignalFile
from shared.toolkit.dossier import Dossier

TIC = 99


def run(clean_dossier: Path, *args: str) -> int:
    workspace = clean_dossier.parent / "ws"
    return main([*args, "--tic", str(TIC), "--workspace", str(workspace)])


@pytest.fixture
def dossier(clean_dossier: Path) -> Path:
    root = clean_dossier.parent / "ws" / "exoplanets" / str(TIC)
    root.mkdir(parents=True)
    (clean_dossier / "lightcurve_clean.parquet").rename(root / "lightcurve_clean.parquet")
    return root


def log(dossier: Path) -> list[LogEntry]:
    return [
        LogEntry.model_validate_json(x) for x in (dossier / "log.jsonl").read_text().splitlines()
    ]


def test_search_select_fold(
    clean_dossier: Path, dossier: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(clean_dossier, "search-period") == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["peaks"][0]["id"] == "p1"
    assert any(d["reason"] == "harmonic" for d in summary["discarded"])
    search = Dossier(dossier).read_envelope("search.json", SearchFile)
    assert "lightcurve_clean.parquet" in search.inputs

    assert run(clean_dossier, "select-peak", "--peak", "p1", "--reason", "highest SNR") == 0
    selected = json.loads(capsys.readouterr().out)
    signal = Dossier(dossier).read_envelope("signal.json", SignalFile)
    assert signal.data.detected
    assert signal.data.period_days == pytest.approx(2.345, rel=1e-3)
    assert selected["peak"] == "p1"
    assert set(signal.inputs) == {"search.json"}

    assert run(clean_dossier, "fold", "--peak", "p1") == 0
    folded = json.loads(capsys.readouterr().out)
    assert folded["depth_ppm"] == pytest.approx(3000.0, rel=0.15)
    assert len(folded["bins"]["rows"]) == 15
    assert set(folded["odd_even"]) == {
        "odd_ppm",
        "even_ppm",
        "difference_ppm",
        "difference_sigma",
        "n_odd",
        "n_even",
    }
    fold_json = next(f for f in folded["files"] if f.endswith(".json"))
    fold = Dossier(dossier).read_envelope(fold_json, FoldFile)
    assert fold.data.peak_id == "p1"
    assert (dossier / fold.data.figure_file).read_bytes().startswith(b"\x89PNG")

    entries = log(dossier)
    assert [e.tool for e in entries] == ["search-period", "select-peak", "fold"]
    assert entries[1].reason == "highest SNR"
    assert entries[1].outputs.keys() == {"signal.json"}
    assert all(e.exit_code == 0 for e in entries)


def test_fold_outputs_are_reproducible(
    clean_dossier: Path, dossier: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for _ in range(2):
        assert (
            run(
                clean_dossier, "fold", "--period", "2.345", "--epoch", "1000.7", "--duration", "2.5"
            )
            == 0
        )
    first, second = log(dossier)
    assert first.outputs == second.outputs


def test_select_peak_below_threshold_exits_2(
    clean_dossier: Path, dossier: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(clean_dossier, "search-period") == 0
    assert run(clean_dossier, "select-peak", "--peak", "p7") == 2
    assert "unknown peak" in capsys.readouterr().err
    assert not (dossier / "signal.json").exists()


def test_select_no_signal(clean_dossier: Path, dossier: Path) -> None:
    assert run(clean_dossier, "search-period") == 0
    assert run(clean_dossier, "select-peak", "--no-signal", "--reason", "only aliases") == 0
    assert not Dossier(dossier).read_envelope("signal.json", SignalFile).data.detected


def test_select_peak_requires_a_choice(clean_dossier: Path, dossier: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        run(clean_dossier, "select-peak")
    assert exc.value.code == 2


def test_search_without_clean_light_curve_exits_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["search-period", "--tic", "5", "--workspace", str(tmp_path)]) == 3
    assert "lightcurve_clean.parquet" in capsys.readouterr().err
