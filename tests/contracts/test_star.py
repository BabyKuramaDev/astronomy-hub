from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import StarData


def neighbor(tic_id: int, sep: float, tmag: float | None = 12.0) -> dict[str, Any]:
    return {"tic_id": tic_id, "separation_arcsec": sep, "tmag": tmag}


@pytest.fixture
def star() -> dict[str, Any]:
    return {
        "ra_deg": 24.35,
        "dec_deg": -45.68,
        "tmag": 8.8,
        "teff_k": {"value": 6200.0, "err_lower": 117.0, "err_upper": 162.0},
        "logg": None,
        "radius_rsun": {"value": 1.35, "err_lower": 0.07, "err_upper": 0.07},
        "mass_msun": None,
        "contamination_ratio": 0.002,
        "source": "TIC v8 (MAST Catalogs)",
        "neighbor_radius_arcsec": 63.0,
        "neighbors": [neighbor(2, 10.0), neighbor(3, 40.0, None)],
    }


def test_valid_star(star: dict[str, Any]) -> None:
    data = StarData.model_validate(star)
    assert data.neighbors[1].tmag is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ra_deg", 360.0),
        ("dec_deg", -91.0),
        ("source", ""),
        ("contamination_ratio", -0.1),
        ("neighbors", [neighbor(2, 40.0), neighbor(3, 10.0)]),
        ("neighbors", [neighbor(2, 70.0)]),
        ("neighbors", [neighbor(2, 1.0), neighbor(2, 2.0)]),
        ("radius_rsun", {"value": 1.0}),
    ],
)
def test_invalid_star_is_rejected(star: dict[str, Any], field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        StarData.model_validate({**star, field: value})
