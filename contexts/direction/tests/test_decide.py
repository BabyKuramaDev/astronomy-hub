import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contexts.direction.cli import main
from contexts.direction.domain.decision import DecisionError, Evidence, decide
from shared.contracts import (
    CatalogData,
    DecisionFile,
    Gate,
    ReviewData,
    SignalData,
    VettingData,
)
from shared.kernel.contexts import Context
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta

TIC = 1234


@pytest.mark.parametrize(
    ("evidence", "final"),
    [
        (Evidence("eval", False, None, None, None), "no_signal"),
        (Evidence("eval", True, "known_planet", "candidate", "reproduced"), "candidate"),
        (Evidence("eval", True, None, "false_positive", None), "false_positive"),
        (Evidence("eval", True, None, "candidate", "partial"), "inconclusive"),
        (Evidence("eval", True, None, "inconclusive", "reproduced"), "inconclusive"),
        (Evidence("explore", True, "known_planet", None, None), "known"),
        (Evidence("explore", True, "toi", None, None), "known"),
        (Evidence("explore", True, "known_false_positive", None, None), "false_positive"),
        (Evidence("explore", True, "unknown", "candidate", "reproduced"), "candidate"),
    ],
)
def test_rule(evidence: Evidence, final: str) -> None:
    assert decide(evidence)[0] == final


@pytest.mark.parametrize(
    ("evidence", "message"),
    [
        (Evidence("explore", True, None, "candidate", "reproduced"), "catalog.json"),
        (Evidence("eval", True, None, None, None), "vetting.json"),
        (Evidence("eval", True, None, "candidate", None), "review.json"),
    ],
)
def test_missing_evidence(evidence: Evidence, message: str) -> None:
    with pytest.raises(DecisionError, match=message):
        decide(evidence)


def meta(context: Context, tool: str) -> ToolMeta:
    return ToolMeta(context, tool, TIC, "exoplanets", "0.1.0", lambda: datetime.now(UTC))


def dossier_with(root: Path, *, catalog: str | None, vetting: str, review: str | None) -> Dossier:
    """signal.json, then the files of later contexts, each computed on that signal.json."""
    d = Dossier(root)
    signal = SignalData(
        detected=True, period_days=2.0, epoch_btjd=1000.0, duration_hours=2.0,
        depth_ppm=1000.0, snr=20.0, n_transits=6, sectors=[1, 2], method="bls", other_peaks=[],
    )  # fmt: skip
    d.write_envelope("signal.json", meta(Context.DETECTION, "select-peak").envelope(signal, {}))

    def write(rel: str, context: Context, data: object) -> None:
        reader = Dossier(root)
        reader.record_read("signal.json")
        reader.write_envelope(rel, meta(context, "t").envelope(data, reader.reads))  # type: ignore[arg-type]

    if catalog:
        write("catalog.json", Context.CATALOG,
              CatalogData(status=catalog, matches=[], literature=[], notes=[]))  # type: ignore[arg-type]  # fmt: skip
    gate = Gate(id="snr", status="pass", severity="soft", value=1.0, threshold=1.0, note="",
                n_runs=1)  # fmt: skip
    write("vetting.json", Context.VETTING,
          VettingData(gates=[gate], verdict=vetting, rationale="r"))  # type: ignore[arg-type]  # fmt: skip
    if review:
        write("review.json", Context.REVIEW, ReviewData(
            period_days_independent=2.0, depth_ppm_independent=1000.0, disagreements=[],
            verdict=review, period_ratio=1.0, depth_ratio=1.0, rationale="r"))  # type: ignore[arg-type]  # fmt: skip
    return d


def run(workspace: Path, mode: str) -> int:
    return main(["decide", "--tic", str(TIC), "--workspace", str(workspace), "--mode", mode,
                 "--reason", "The rule says so."])  # fmt: skip


def root(workspace: Path) -> Path:
    return workspace / "exoplanets" / str(TIC)


def test_eval_mode_never_reads_the_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dossier_with(root(tmp_path), catalog="known_planet", vetting="candidate", review="reproduced")
    assert run(tmp_path, "eval") == 0
    summary = json.loads(capsys.readouterr().out)
    decision = Dossier(root(tmp_path)).read_envelope("decision.json", DecisionFile)
    assert decision.data.final == "candidate" == summary["final"]
    assert decision.data.mode == "eval"
    assert decision.data.reason == "The rule says so."
    assert "catalog.json" not in decision.inputs


def test_explore_mode_cuts_on_the_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dossier_with(root(tmp_path), catalog="known_planet", vetting="candidate", review="reproduced")
    assert run(tmp_path, "explore") == 0
    assert json.loads(capsys.readouterr().out)["final"] == "known"


def test_false_positive_does_not_need_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dossier_with(root(tmp_path), catalog=None, vetting="false_positive", review=None)
    assert run(tmp_path, "eval") == 0
    assert json.loads(capsys.readouterr().out)["final"] == "false_positive"


def test_stale_vetting_is_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dossier_with(root(tmp_path), catalog=None, vetting="candidate", review="reproduced")
    signal = root(tmp_path) / "signal.json"
    signal.write_text(signal.read_text().replace('"snr": 20.0', '"snr": 25.0'))
    assert run(tmp_path, "eval") == 2
    assert "another signal.json" in capsys.readouterr().err


def test_no_signal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = SignalData(detected=False, sectors=[1], method="bls", other_peaks=[])
    Dossier(root(tmp_path)).write_envelope(
        "signal.json", meta(Context.DETECTION, "select-peak").envelope(data, {})
    )
    assert run(tmp_path, "explore") == 0
    assert json.loads(capsys.readouterr().out)["final"] == "no_signal"


def test_a_catalog_cut_ignores_leftover_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """vetting.json of an earlier run is stale, but explore cuts on the catalog first."""
    dossier_with(root(tmp_path), catalog=None, vetting="candidate", review="reproduced")
    signal = root(tmp_path) / "signal.json"
    signal.write_text(signal.read_text().replace('"snr": 20.0', '"snr": 25.0'))
    reader = Dossier(root(tmp_path))
    reader.record_read("signal.json")
    data = CatalogData(status="known_planet", matches=[], literature=[], notes=[])
    reader.write_envelope(
        "catalog.json", meta(Context.CATALOG, "crossmatch").envelope(data, reader.reads)
    )
    assert run(tmp_path, "explore") == 0
    assert json.loads(capsys.readouterr().out)["final"] == "known"
    assert (
        "vetting.json"
        not in Dossier(root(tmp_path)).read_envelope("decision.json", DecisionFile).inputs
    )


def test_package_dossier(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import tarfile

    dossier_with(root(tmp_path), catalog=None, vetting="false_positive", review=None)
    (root(tmp_path) / ".cache").mkdir()
    (root(tmp_path) / ".cache" / "junk").write_text("x")
    dest = tmp_path / "outputs"
    argv = ["package-dossier", "--tic", str(TIC), "--workspace", str(tmp_path), "--dest", str(dest)]
    assert main(argv) == 3  # no decision.json yet
    capsys.readouterr()
    assert run(tmp_path, "eval") == 0
    capsys.readouterr()
    assert main(argv) == 0
    summary = json.loads(capsys.readouterr().out)
    archive = dest / f"dossier-{TIC}.tar.gz"
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert f"{TIC}/decision.json" in names
    assert not any(".cache" in n for n in names)
    assert set(summary["validated"]) == {"signal.json", "vetting.json", "decision.json"}
    with tarfile.open(archive) as tar:
        member = tar.extractfile(f"{TIC}/log.jsonl")
        assert member is not None
        shipped = member.read().decode().splitlines()
    assert json.loads(shipped[-1])["tool"] == "package-dossier", "its own line travels in the tar"
    local = (root(tmp_path) / "log.jsonl").read_text().splitlines()
    ok = [json.loads(x) for x in local]
    assert [e["tool"] for e in ok if e["exit_code"] == 0].count("package-dossier") == 1


def test_pack_is_deterministic(tmp_path: Path) -> None:
    from contexts.direction.infrastructure.tarball import pack

    src = tmp_path / "123"
    (src / "folds").mkdir(parents=True)
    (src / "a.json").write_text("{}")
    (src / "folds" / "b.json").write_text("[]")
    first = pack(src, ["folds/b.json", "a.json"], tmp_path / "x.tar.gz")
    (src / "a.json").touch()  # a new mtime must not change the archive
    assert pack(src, ["a.json", "folds/b.json"], tmp_path / "y.tar.gz") == first


def test_package_dossier_rejects_an_invalid_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dossier_with(root(tmp_path), catalog=None, vetting="false_positive", review=None)
    assert run(tmp_path, "eval") == 0
    (root(tmp_path) / "vetting.json").write_text('{"broken": true}')
    argv = ["package-dossier", "--tic", str(TIC), "--workspace", str(tmp_path),
            "--dest", str(tmp_path / "out")]  # fmt: skip
    capsys.readouterr()
    assert main(argv) == 2
    assert "vetting.json does not match its contract" in capsys.readouterr().err
