import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from contexts.review.cli import main
from contexts.review.domain.comparison import Tolerances, alias, compare
from shared.contracts import (
    LightcurveSetData,
    ReproductionData,
    ReproductionFile,
    ReviewFile,
    SectorLightcurve,
    SignalData,
)
from shared.kernel.contexts import Context
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta
from tests.support.synthetic import Transit, light_curve

TIC = 515
TOL = Tolerances(period=0.001, depth=0.2, alias_max_integer=10)
TRANSIT = Transit(period_days=1.83, epoch_btjd=1000.4, duration_hours=2.0, depth_ppm=4000.0)


def meta(context: Context, tool: str) -> ToolMeta:
    return ToolMeta(context, tool, TIC, "exoplanets", "0.1.0", lambda: datetime.now(UTC))


@pytest.mark.parametrize(
    ("ratio", "expected"), [(2.0, "2/1"), (0.5, "1/2"), (3.0005, "3/1"), (1.5, None), (1.0, None)]
)
def test_alias(ratio: float, expected: str | None) -> None:
    assert alias(ratio, 0.001, 10) == expected


@pytest.mark.parametrize(
    ("period", "depth", "verdict"),
    [
        (2.0001, 1100.0, "reproduced"),
        (2.0001, 1500.0, "partial"),  # depth 50% off
        (4.0002, 1000.0, "partial"),  # 2/1 alias
        (2.1, 1000.0, "not_reproduced"),
    ],
)
def test_compare(period: float, depth: float, verdict: str) -> None:
    result = compare(
        True,
        period,
        depth,
        20.0,
        9.0,
        2.0,
        1000.0,
        TOL,
        epoch=1000.0,
        signal_epoch=1000.0,
        signal_duration_hours=2.0,
    )
    assert result.verdict == verdict
    assert (result.disagreements == ()) == (verdict == "reproduced")


@pytest.mark.parametrize(
    ("epoch", "verdict"),
    [
        (1000.03, "reproduced"),  # 0.36 durations off
        (1020.0001, "reproduced"),  # ten periods later, the same transit times
        (1001.0, "partial"),  # half a period off: another signal on the same period
        (None, "partial"),  # no epoch to check
    ],
)
def test_compare_checks_the_transit_times(epoch: float | None, verdict: str) -> None:
    result = compare(
        True,
        2.0,
        1000.0,
        20.0,
        9.0,
        2.0,
        1000.0,
        TOL,
        epoch=epoch,
        signal_epoch=1000.0,
        signal_duration_hours=2.0,
    )
    assert result.verdict == verdict
    if verdict == "partial":
        assert "other times" in result.disagreements[0]


def test_compare_without_detection() -> None:
    result = compare(False, None, None, 6.2, 9.0, 2.0, 1000.0, TOL)
    assert result.verdict == "not_reproduced"
    assert "SDE >= 9" in result.disagreements[0]


def root(workspace: Path) -> Path:
    return workspace / "exoplanets" / str(TIC)


def write_raw(root_dir: Path, transit: Transit | None, seed: int = 3) -> None:
    """Two 8-day sectors of raw flux (with a slow trend) and their manifest."""
    dossier = Dossier(root_dir)
    entries = []
    for k, sector in enumerate((40, 41)):
        time, flux, err = light_curve(
            start=1000.0 + 9.0 * k,
            days=8.0,
            noise_ppm=500.0,
            transit=transit,
            trend_amplitude=0.002,
            seed=seed + k,
        )
        rel = f"lightcurve/s{sector:04d}.parquet"
        nan = np.full(time.size, np.nan)
        dossier.write_table(
            rel,
            {
                "time_btjd": time,
                "flux": flux * 3e4,
                "flux_err": err * 3e4,
                "centroid_col": nan,
                "centroid_row": nan,
            },
        )
        entries.append(
            SectorLightcurve(
                sector=sector,
                fits_file=f"lightcurve/s{sector}.fits",
                table_file=rel,
                n_cadences=time.size,
                n_valid=time.size,
                t_start_btjd=float(time[0]),
                t_end_btjd=float(time[-1]),
            )
        )
    manifest = LightcurveSetData(
        author="SPOC",
        exptime_s=120.0,
        flux_column="PDCSAP_FLUX",
        available_sectors=[40, 41],
        selection_rule="longest_consecutive_run",
        max_sectors=4,
        sectors=entries,
    )
    dossier.write_envelope(
        "lightcurve/manifest.json",
        meta(Context.ACQUISITION, "fetch-lightcurves").envelope(manifest, {}),
    )


def write_signal(root_dir: Path, period: float, depth: float) -> None:
    signal = SignalData(
        detected=True,
        period_days=period,
        epoch_btjd=1000.4,
        duration_hours=2.0,
        depth_ppm=depth,
        snr=30.0,
        n_transits=8,
        sectors=[40, 41],
        method="bls",
        other_peaks=[],
    )
    Dossier(root_dir).write_envelope(
        "signal.json", meta(Context.DETECTION, "select-peak").envelope(signal, {})
    )


def run(workspace: Path, *argv: str) -> int:
    tool, *extra = argv
    return main([tool, "--tic", str(TIC), "--workspace", str(workspace), *extra])


def test_reproduce_finds_the_transit_without_reading_the_signal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_raw(root(tmp_path), TRANSIT)
    write_signal(root(tmp_path), 1.83, 3600.0)
    assert run(tmp_path, "reproduce") == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["detected"]
    assert summary["period_days"] == pytest.approx(TRANSIT.period_days, rel=1e-3)
    env = Dossier(root(tmp_path)).read_envelope("review/reproduction.json", ReproductionFile)
    assert "signal.json" not in env.inputs
    assert set(env.inputs) == {
        "lightcurve/manifest.json",
        "lightcurve/s0040.parquet",
        "lightcurve/s0041.parquet",
    }
    assert run(tmp_path, "conclude", "--rationale", "TLS agrees.") == 0
    review = Dossier(root(tmp_path)).read_envelope("review.json", ReviewFile).data
    assert review.verdict == "reproduced"
    assert review.rationale == "TLS agrees."
    assert env.data.box_depth_ppm == pytest.approx(TRANSIT.depth_ppm, rel=0.2)
    assert review.depth_ppm_independent == env.data.box_depth_ppm
    assert abs(review.epoch_offset_durations or 9) < 0.5


def test_reproduce_without_a_transit_finds_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_raw(root(tmp_path), None)
    assert run(tmp_path, "reproduce") == 0
    assert json.loads(capsys.readouterr().out)["detected"] is False


def _reproduction(root_dir: Path, period: float | None, depth: float | None) -> None:
    detected = period is not None
    data = ReproductionData(
        detrend_method="median",
        detrend_window_days=1.0,
        search_method="tls",
        sectors=[40],
        period_min_days=0.5,
        period_max_days=7.0,
        detected=detected,
        sde_min=9.0,
        period_days=period,
        epoch_btjd=1000.4 if detected else None,
        duration_hours=2.0 if detected else None,
        depth_ppm=None if depth is None else 2 * depth,
        sde=30.0 if detected else 5.0,
        snr=20.0 if detected else None,
        n_transits=8 if detected else None,
        box_depth_ppm=depth,  # TLS's depth_ppm (a model depth) is never compared
    )
    Dossier(root_dir).write_envelope(
        "review/reproduction.json", meta(Context.REVIEW, "reproduce").envelope(data, {})
    )


@pytest.mark.parametrize(
    ("period", "depth", "verdict"),
    [(1.83, 3700.0, "reproduced"), (3.66, 3700.0, "partial"), (None, None, "not_reproduced")],
)
def test_conclude_rule(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    period: float | None,
    depth: float | None,
    verdict: str,
) -> None:
    write_signal(root(tmp_path), 1.83, 3600.0)
    _reproduction(root(tmp_path), period, depth)
    assert run(tmp_path, "conclude", "--rationale", "r") == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == verdict


def test_conclude_needs_reproduce(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_signal(root(tmp_path), 1.83, 3600.0)
    assert run(tmp_path, "conclude", "--rationale", "r") == 2
    assert "run reproduce first" in capsys.readouterr().err
