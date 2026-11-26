import json
from pathlib import Path

import pytest

from contexts.vetting.cli import main
from contexts.vetting.domain.gates import GATE_IDS
from contexts.vetting.domain.verdict import GateStatus, combine, verdict
from contexts.vetting.tests.conftest import TIC, meta, write_vetting_dossier
from shared.contracts import (
    GateRun,
    GateRunsData,
    GateRunsFile,
    LogEntry,
    SignalData,
    VettingFile,
)
from shared.kernel.contexts import Context
from shared.toolkit.dossier import Dossier


def run(workspace: Path, tool: str, *extra: str) -> int:
    return main([tool, "--tic", str(TIC), "--workspace", str(workspace), *extra])


def root(workspace: Path) -> Path:
    return workspace / "exoplanets" / str(TIC)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    write_vetting_dossier(root(tmp_path))
    return tmp_path


def out(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [(["pass"], "pass"), (["fail", "fail"], "fail"), (["pass", "fail"], "marginal"),
     (["marginal"], "marginal"), (["pass", "marginal"], "marginal")],
)  # fmt: skip
def test_combine(statuses: list[str], expected: str) -> None:
    assert combine(statuses) == expected


@pytest.mark.parametrize(
    ("gates", "expected"),
    [
        ([("a", "pass", "hard"), ("b", "pass", "soft"), ("c", "fail", "info")], "candidate"),
        ([("a", "fail", "hard"), ("b", "marginal", "soft")], "false_positive"),
        ([("a", "pass", "hard"), ("b", "fail", "soft")], "inconclusive"),
        ([("a", "marginal", "hard"), ("b", "pass", "soft")], "inconclusive"),
    ],
)
def test_verdict_rule(gates: list[tuple[str, str, str]], expected: str) -> None:
    assert verdict([GateStatus(*g) for g in gates]) == expected


def test_run_gates_then_conclude(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(workspace, "run-gates") == 0
    summary = out(capsys)
    assert [g["gate"] for g in summary["gates"]] == list(GATE_IDS)
    assert summary["verdict_if_concluded"] == "candidate"
    runs = Dossier(root(workspace)).read_envelope("vetting/runs.json", GateRunsFile)
    assert {"signal.json", "search.json", "star.json", "lightcurve_clean.parquet"} <= set(
        runs.inputs
    )
    assert run(workspace, "conclude", "--rationale", "Every gate passes.") == 0
    assert out(capsys)["verdict"] == "candidate"
    vetting = Dossier(root(workspace)).read_envelope("vetting.json", VettingFile).data
    assert vetting.verdict == "candidate"
    assert vetting.rationale == "Every gate passes."
    assert {g.id: g.severity for g in vetting.gates}["catalog"] == "info"
    last = LogEntry.model_validate_json(
        (root(workspace) / "log.jsonl").read_text().splitlines()[-1]
    )
    assert last.reason == "Every gate passes."


def test_run_gate_adds_runs_once(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(workspace, "run-gates") == 0
    capsys.readouterr()
    assert run(workspace, "run-gate", "--gate", "odd-even", "--duration-scale", "0.8") == 0
    first = out(capsys)
    assert first["run"]["run"] == 2
    assert first["params"] == {"duration-scale": 0.8, "window-durations": 4.0}
    assert run(workspace, "run-gate", "--gate", "odd-even", "--duration-scale", "0.8") == 0
    assert out(capsys)["gate_runs"] == first["gate_runs"]  # same parameters: same run
    runs = Dossier(root(workspace)).read_envelope("vetting/runs.json", GateRunsFile).data
    assert len(runs.of("odd-even")) == 2
    assert run(workspace, "conclude", "--rationale", "r") == 0
    vetting = Dossier(root(workspace)).read_envelope("vetting.json", VettingFile).data
    gate = next(g for g in vetting.gates if g.id == "odd-even")
    assert gate.n_runs == 2


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--gate", "coverage"], "no measurement parameters"),
        (["--gate", "plausibility"], "no measurement parameters"),
        (["--gate", "nope"], "unknown gate"),
        (["--gate", "odd-even", "--duration-scale", "3"], "within"),
    ],
)
def test_run_gate_rejects(
    workspace: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str
) -> None:
    assert run(workspace, "run-gates") == 0
    capsys.readouterr()
    assert run(workspace, "run-gate", *extra) == 2
    assert message in capsys.readouterr().err


def test_run_gate_needs_run_gates(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(workspace, "run-gate", "--gate", "odd-even") == 2
    assert "run run-gates first" in capsys.readouterr().err


def test_mixed_runs_are_marginal_and_inconclusive(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(workspace, "run-gates") == 0
    dossier = Dossier(root(workspace))
    env = dossier.read_envelope("vetting/runs.json", GateRunsFile)
    first = env.data.of("odd-even")[0]
    flipped = GateRun(**{**first.model_dump(), "run": 2, "status": "fail", "params": {"x": 1.0}})
    data = GateRunsData(runs=[*env.data.runs, flipped])
    dossier.write_envelope("vetting/runs.json", env.model_copy(update={"data": data}))
    assert run(workspace, "conclude", "--rationale", "r") == 0
    vetting = dossier.read_envelope("vetting.json", VettingFile).data
    assert next(g for g in vetting.gates if g.id == "odd-even").status == "marginal"
    assert vetting.verdict == "inconclusive"


def test_conclude_rejects_runs_of_another_signal(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(workspace, "run-gates") == 0
    signal = root(workspace) / "signal.json"
    signal.write_text(signal.read_text().replace('"snr": 20.0', '"snr": 21.0'))
    capsys.readouterr()
    assert run(workspace, "conclude", "--rationale", "r") == 2
    assert "another signal.json" in capsys.readouterr().err


def test_conclude_needs_a_rationale(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(workspace, "run-gates") == 0
    assert run(workspace, "conclude", "--rationale", "  ") == 2


def test_no_signal_is_not_vetted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dossier = write_vetting_dossier(root(tmp_path))
    data = SignalData(detected=False, sectors=[6], method="bls", other_peaks=[])
    dossier.write_envelope("signal.json", meta(Context.DETECTION, "select-peak").envelope(data, {}))
    assert run(tmp_path, "run-gates") == 2
    assert "nothing to vet" in capsys.readouterr().err


def test_eclipsing_binary_dossier_is_a_false_positive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_vetting_dossier(root(tmp_path), odd_depth=950e-6, even_depth=200e-6)
    assert run(tmp_path, "run-gates") == 0
    assert run(tmp_path, "conclude", "--rationale", "Odd and even depths differ.") == 0
    assert Dossier(root(tmp_path)).read_envelope("vetting.json", VettingFile).data.verdict == (
        "false_positive"
    )
