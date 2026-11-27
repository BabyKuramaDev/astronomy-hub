import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from contexts.followup.cli import main
from contexts.followup.domain.ephemeris import btjd_to_utc, next_transits, utc_to_btjd
from shared.contracts import EphemerisFile, Measurement, ModelData
from shared.kernel.contexts import Context
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta

TIC = 909


def m(value: float, err: float) -> Measurement:
    return Measurement(value=value, err_lower=err, err_upper=err)


def test_btjd_round_trip() -> None:
    moment = datetime(2026, 11, 26, 6, 30, tzinfo=UTC)
    assert btjd_to_utc(utc_to_btjd(moment)) == moment


def test_errors_grow_with_the_number_of_periods() -> None:
    start = btjd_to_utc(1000.0)
    transits = next_transits(
        epoch=1000.5,
        epoch_err=1e-3,
        period=2.0,
        period_err=1e-4,
        duration_hours=3.0,
        start=start,
        horizon_days=10.0,
        max_transits=20,
    )
    assert [t.n for t in transits] == [0, 1, 2, 3, 4]
    assert transits[0].err_minutes == pytest.approx(1e-3 * 1440)
    assert transits[4].err_minutes == pytest.approx((1e-6 + (4e-4) ** 2) ** 0.5 * 1440)
    assert transits[1].mid_btjd == pytest.approx(1002.5)
    assert transits[1].egress_utc - transits[1].ingress_utc == timedelta(hours=3)


def test_max_transits() -> None:
    transits = next_transits(
        epoch=1000.5,
        epoch_err=0.0,
        period=0.5,
        period_err=0.0,
        duration_hours=1.0,
        start=btjd_to_utc(1099.9),
        horizon_days=30.0,
        max_transits=3,
    )
    assert [t.n for t in transits] == [199, 200, 201]


def write_model(root: Path) -> None:
    data = ModelData(
        method="quick",
        rp_rs=m(0.1, 0.001),
        planet_radius_rearth=None,
        impact_parameter=m(0.3, 0.02),
        a_rs=m(5.0, 0.1),
        period_days=m(2.0, 1e-5),
        epoch_btjd=m(utc_to_btjd(datetime(2026, 11, 1, tzinfo=UTC)), 2e-4),
        duration_hours=m(2.5, 0.05),
        jitter_ppm=m(10.0, 1.0),
        stellar_source=None,
        convergence=None,
    )
    meta = ToolMeta(Context.MODELING, "fit-transit", TIC, "exoplanets", "0.1.0")
    Dossier(root).write_envelope("model.json", meta.envelope(data, {}))


def test_ephemeris_tool(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "exoplanets" / str(TIC)
    write_model(root)
    argv = ["ephemeris", "--tic", str(TIC), "--workspace", str(tmp_path), "--start", "2026-12-01"]
    assert main(argv) == 0
    summary = json.loads(capsys.readouterr().out)
    data = Dossier(root).read_envelope("ephemeris.json", EphemerisFile).data
    assert data.start_utc == datetime(2026, 12, 1, tzinfo=UTC)
    assert len(data.transits) == 15  # one every 2 days for 30 days
    assert all(t.mid_utc >= data.start_utc for t in data.transits)
    assert summary["transits"][0][0] == data.transits[0].n
    assert main(argv) == 0  # idempotent: same start, same output
    lines = (root / "log.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["outputs"] == json.loads(lines[1])["outputs"]


def test_ephemeris_needs_a_model(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ephemeris", "--tic", str(TIC), "--workspace", str(tmp_path)]) == 3
    assert "model.json not found" in capsys.readouterr().err


def test_ephemeris_refuses_a_failed_fit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "exoplanets" / str(TIC)
    data = ModelData(
        method="quick",
        status="failed",
        failure="no valid samples to summarize",
        rp_rs=None,
        planet_radius_rearth=None,
        impact_parameter=None,
        a_rs=None,
        period_days=None,
        epoch_btjd=None,
        duration_hours=None,
        jitter_ppm=None,
        stellar_source=None,
        convergence=None,
    )
    meta = ToolMeta(Context.MODELING, "fit-transit", TIC, "exoplanets", "0.1.0")
    Dossier(root).write_envelope("model.json", meta.envelope(data, {}))
    assert main(["ephemeris", "--tic", str(TIC), "--workspace", str(tmp_path)]) == 2
    assert "failed fit" in capsys.readouterr().err
