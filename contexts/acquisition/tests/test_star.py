import math

import pytest

from contexts.acquisition.domain.star import build_star, measurement


def test_measurement_prefers_asymmetric_errors() -> None:
    row = {"rad": 1.3, "e_rad": 0.1, "eneg_Rad": 0.05, "epos_Rad": 0.2}
    m = measurement(row, "rad", "e_rad", "eneg_Rad", "epos_Rad")
    assert m is not None
    assert (m.value, m.err_lower, m.err_upper) == (1.3, 0.05, 0.2)


def test_measurement_falls_back_to_symmetric_error() -> None:
    row = {"rad": 1.3, "e_rad": 0.1, "eneg_Rad": None, "epos_Rad": math.nan}
    m = measurement(row, "rad", "e_rad", "eneg_Rad", "epos_Rad")
    assert m is not None
    assert (m.err_lower, m.err_upper) == (0.1, 0.1)


@pytest.mark.parametrize(
    "row",
    [
        {"rad": None, "e_rad": 0.1},
        {"rad": 1.3, "e_rad": None},
        {"rad": math.nan, "e_rad": 0.1},
        {},
    ],
)
def test_measurement_needs_value_and_error(row: dict) -> None:
    assert measurement(row, "rad", "e_rad", "eneg_Rad", "epos_Rad") is None


def test_build_star_filters_and_sorts_neighbors() -> None:
    target = {"ID": 10, "ra": 24.35, "dec": -45.68, "Tmag": 8.8, "rad": 1.3, "e_rad": 0.07}
    rows = [
        {"ID": 10, "dstArcSec": 0.0, "Tmag": 8.8},  # the target itself
        {"ID": 12, "dstArcSec": 30.0, "Tmag": 14.0},
        {"ID": 11, "dstArcSec": 5.0, "Tmag": None},
        {"ID": 13, "dstArcSec": 80.0, "Tmag": 12.0},  # outside the radius
    ]
    star = build_star(target, rows, 63.0, "MAST TIC (version 20190415)")
    assert [n.tic_id for n in star.neighbors] == [11, 12]
    assert star.radius_rsun is not None
    assert star.teff_k is None
    assert star.source.startswith("MAST TIC")


def test_build_star_requires_coordinates() -> None:
    with pytest.raises(ValueError, match="coordinates"):
        build_star({"ID": 1, "ra": None, "dec": 1.0}, [], 63.0, "src")
