from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import LightcurveSetData


def sector(n: int, **overrides: Any) -> dict[str, Any]:
    base = {
        "sector": n,
        "fits_file": f"lightcurve/s{n:04d}.fits",
        "table_file": f"lightcurve/s{n:04d}.parquet",
        "n_cadences": 100,
        "n_valid": 90,
        "t_start_btjd": 1000.0,
        "t_end_btjd": 1025.0,
    }
    return {**base, **overrides}


@pytest.fixture
def manifest() -> dict[str, Any]:
    return {
        "author": "SPOC",
        "exptime_s": 120.0,
        "flux_column": "PDCSAP_FLUX",
        "available_sectors": [2, 3, 29],
        "selection_rule": "longest_consecutive_run",
        "max_sectors": 4,
        "sectors": [sector(2), sector(3)],
    }


def test_valid_manifest(manifest: dict[str, Any]) -> None:
    assert [s.sector for s in LightcurveSetData.model_validate(manifest).sectors] == [2, 3]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("flux_column", "SAP_FLUX"),
        ("selection_rule", "all"),
        ("available_sectors", [3, 2]),
        ("sectors", []),
        ("sectors", [sector(3), sector(2)]),
        ("sectors", [sector(5)]),
        ("sectors", [sector(2, n_valid=101)]),
        ("sectors", [sector(2, t_end_btjd=999.0)]),
        ("sectors", [sector(2, fits_file="/abs/x.fits")]),
        ("max_sectors", 1),
    ],
)
def test_invalid_manifest_is_rejected(manifest: dict[str, Any], field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        LightcurveSetData.model_validate({**manifest, field: value})
