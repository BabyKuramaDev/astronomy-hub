from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import PeriodSearchData


def peak(n: int, period: float = 1.0) -> dict[str, Any]:
    return {
        "id": f"p{n}",
        "period_days": period,
        "epoch_btjd": 1001.0,
        "duration_hours": 2.0,
        "depth_ppm": 1000.0,
        "snr": 20.0,
        "sde": 12.0,
        "n_transits": 10,
        "power": 50.0,
    }


def discarded(**overrides: Any) -> dict[str, Any]:
    base = {
        "period_days": 2.0,
        "epoch_btjd": 1001.0,
        "duration_hours": 2.0,
        "depth_ppm": 500.0,
        "snr": 9.0,
        "sde": 4.0,
        "power": 20.0,
        "reason": "harmonic",
        "harmonic_of": "p1",
        "ratio": "2/1",
    }
    return {**base, **overrides}


@pytest.fixture
def search() -> dict[str, Any]:
    return {
        "method": "bls",
        "sectors": [2, 3],
        "period_min_days": 0.5,
        "period_max_days": 15.0,
        "durations_hours": [1.0, 2.0],
        "bin_minutes": 10.0,
        "n_periods": 10000,
        "inverted_snr_max": 9.5,
        "peaks": [peak(1), peak(2, 3.3)],
        "discarded": [
            discarded(),
            discarded(reason="non_positive_depth", depth_ppm=-5.0, harmonic_of=None, ratio=None),
        ],
    }


def test_valid_search(search: dict[str, Any]) -> None:
    data = PeriodSearchData.model_validate(search)
    assert data.peak("p2") is not None
    assert data.peak("p9") is None


def test_no_peaks_is_valid(search: dict[str, Any]) -> None:
    assert PeriodSearchData.model_validate({**search, "peaks": [], "discarded": []})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("peaks", [peak(2)]),
        ("peaks", [peak(1), peak(1)]),
        ("peaks", [{**peak(1), "depth_ppm": 0.0}]),
        ("peaks", [{**peak(1), "depth_ppm": -10.0}]),
        ("discarded", [discarded(harmonic_of="p7")]),
        ("discarded", [discarded(ratio=None)]),
        ("discarded", [discarded(ratio="2:1")]),
        ("discarded", [discarded(reason="non_positive_depth", harmonic_of=None, ratio=None)]),
        ("discarded", [discarded(reason="noise")]),
        ("period_max_days", 0.5),
    ],
)
def test_invalid_search_is_rejected(search: dict[str, Any], field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        PeriodSearchData.model_validate({**search, field: value})
