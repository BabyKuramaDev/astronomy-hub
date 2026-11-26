import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contexts.reporting.cli import main
from contexts.reporting.domain.view import compact, measurement, num
from shared.contracts import DecisionData, Measurement, SignalData
from shared.kernel.contexts import Context
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta

TIC = 321


def meta(context: Context, tool: str) -> ToolMeta:
    return ToolMeta(context, tool, TIC, "exoplanets", "0.1.0", lambda: datetime.now(UTC))


@pytest.mark.parametrize(
    ("value", "digits", "text"),
    [(0.94145223, 7, "0.9414522"), (9732.7, 4, "9733"), (None, 4, "\u2013"), (0.0, 3, "0")],
)
def test_num(value: float | None, digits: int, text: str) -> None:
    assert num(value, digits) == text


def test_measurement_and_compact() -> None:
    assert measurement(Measurement(value=0.1, err_lower=0.002, err_upper=0.002), 3) == (
        "0.100 \u00b1 0.0020"
    )
    assert measurement(Measurement(value=2.0, err_lower=0.1, err_upper=0.3), 3) == (
        "2.00 (\u22120.10 / +0.30)"
    )
    assert compact(93.0) == "93"
    assert compact(0.028) == "0.028"


def write(root: Path, final: str = "no_signal") -> None:
    d = Dossier(root)
    signal = SignalData(detected=False, sectors=[3], method="bls", other_peaks=[])
    d.write_envelope("signal.json", meta(Context.DETECTION, "select-peak").envelope(signal, {}))
    decision = DecisionData(mode="explore", final=final, reason="No peak passes select-peak.",  # type: ignore[arg-type]
                            next_step="Revisit with new sectors.")  # fmt: skip
    d.write_envelope("decision.json", meta(Context.DIRECTION, "decide").envelope(decision, {}))


def run(workspace: Path, *extra: str) -> int:
    return main(["render-report", "--tic", str(TIC), "--workspace", str(workspace), *extra])


def test_report_starts_with_the_verdict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "exoplanets" / str(TIC)
    write(root)
    assert run(tmp_path, "--summary", "Nothing periodic in sector 3.") == 0
    summary = json.loads(capsys.readouterr().out)
    text = (root / "report.md").read_text()
    assert text.startswith(f"# TIC {TIC}: no_signal\n\n**Verdict: no signal**")
    assert "Nothing periodic in sector 3." in text
    assert "`detected=false`" in text
    assert "`vetting.json` is not in the dossier." in text
    assert "vetting.json" in summary["sections_missing"]
    assert "discover" not in text.lower()
    log = json.loads((root / "log.jsonl").read_text().splitlines()[-1])
    assert "report.md" in log["outputs"]


def test_report_needs_a_decision(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(tmp_path) == 2
    assert "run decide before render-report" in capsys.readouterr().err
