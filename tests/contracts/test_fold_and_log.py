from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import FoldData, LogEntry

SHA = "sha256:" + "1" * 64


@pytest.fixture
def fold() -> dict[str, Any]:
    empty_odd_even = {
        "depth_odd_ppm": None,
        "depth_odd_err_ppm": None,
        "depth_even_ppm": None,
        "depth_even_err_ppm": None,
        "difference_ppm": None,
        "difference_sigma": None,
        "n_odd": 0,
        "n_even": 0,
    }
    return {
        "source": "peak",
        "peak_id": "p1",
        "period_days": 1.0,
        "epoch_btjd": 1000.5,
        "duration_hours": 2.0,
        "n_points": 0,
        "n_transits_covered": 0,
        "in_transit_depth_ppm": None,
        "oot_scatter_ppm": None,
        "bins": [{"phase_hours": 0.0, "depth_ppm": None, "depth_err_ppm": None, "n_points": 0}],
        "odd_even": empty_odd_even,
        "data_file": "folds/P1.000000.parquet",
        "figure_file": "figures/fold_P1.000000.png",
    }


def test_valid_fold(fold: dict[str, Any]) -> None:
    assert FoldData.model_validate(fold).peak_id == "p1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "manual"},
        {"peak_id": None},
        {"figure_file": "../x.png"},
    ],
)
def test_invalid_fold_is_rejected(fold: dict[str, Any], overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FoldData.model_validate({**fold, **overrides})


@pytest.fixture
def log_entry() -> dict[str, Any]:
    return {
        "ts": "2026-11-26T12:00:00Z",
        "context": "detection",
        "tool": "select-peak",
        "argv": ["select-peak", "--tic", "1", "--peak", "p1"],
        "version": "0.1.0+gabc1234",
        "duration_s": 0.2,
        "exit_code": 0,
        "outputs": {"signal.json": SHA},
        "summary": {"detected": True, "period_days": 0.94},
        "reason": "Highest SNR, no harmonics.",
        "error": None,
    }


def test_valid_log_entry(log_entry: dict[str, Any]) -> None:
    assert LogEntry.model_validate(log_entry).reason


@pytest.mark.parametrize(
    "overrides",
    [
        {"ts": "2026-11-26T09:00:00-03:00"},
        {"context": "astrology"},
        {"outputs": {"/abs": SHA}},
        {"duration_s": -1.0},
    ],
)
def test_invalid_log_entry_is_rejected(
    log_entry: dict[str, Any], overrides: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        LogEntry.model_validate({**log_entry, **overrides})
