from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import EphemerisData


def transit(n: int) -> dict[str, Any]:
    return {
        "n": n,
        "mid_btjd": 3400.0 + n,
        "mid_utc": "2026-12-01T10:00:00Z",
        "ingress_utc": "2026-12-01T09:00:00Z",
        "egress_utc": "2026-12-01T11:00:00Z",
        "err_minutes": 0.8,
    }


@pytest.fixture
def ephemeris() -> dict[str, Any]:
    m = {"value": 0.94145, "err_lower": 1e-6, "err_upper": 1e-6}
    return {
        "model_method": "mcmc",
        "period_days": m,
        "epoch_btjd": {"value": 3300.1, "err_lower": 1e-4, "err_upper": 1e-4},
        "duration_hours": 2.19,
        "start_utc": "2026-11-26T00:00:00Z",
        "horizon_days": 30.0,
        "transits": [transit(1), transit(2)],
    }


def test_valid_ephemeris(ephemeris: dict[str, Any]) -> None:
    assert len(EphemerisData.model_validate(ephemeris).transits) == 2


def test_transits_are_ordered(ephemeris: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="ordered"):
        EphemerisData.model_validate({**ephemeris, "transits": [transit(2), transit(1)]})


def test_times_are_utc(ephemeris: dict[str, Any]) -> None:
    bad = {**transit(1), "mid_utc": "2026-12-01T10:00:00+03:00"}
    with pytest.raises(ValidationError, match="UTC"):
        EphemerisData.model_validate({**ephemeris, "transits": [bad]})
