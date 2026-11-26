from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import Measurement, ModelData


def m(value: float, lower: float = 0.01, upper: float = 0.02) -> dict[str, float]:
    return {"value": value, "err_lower": lower, "err_upper": upper}


@pytest.fixture
def model_data() -> dict[str, Any]:
    return {
        "rp_rs": m(0.097),
        "planet_radius_rearth": m(13.2, 0.4, 0.5),
        "impact_parameter": m(0.36, 0.05, 0.04),
        "a_rs": m(3.48, 0.03, 0.03),
        "stellar_source": "TIC v8.2",
    }


def test_valid_model(model_data: dict[str, Any]) -> None:
    model = ModelData.model_validate(model_data)
    assert model.planet_radius_rearth == Measurement(value=13.2, err_lower=0.4, err_upper=0.5)


def test_zero_errors_are_allowed() -> None:
    assert Measurement(value=1.0, err_lower=0.0, err_upper=0.0).err_lower == 0.0


@pytest.mark.parametrize(
    "measurement",
    [
        m(1.0, lower=-0.1),
        m(1.0, upper=-0.1),
        m(float("nan")),
        {"value": 1.0, "err_lower": 0.1},
        {**m(1.0), "err": 0.1},
    ],
)
def test_invalid_measurement_is_rejected(
    model_data: dict[str, Any], measurement: dict[str, float]
) -> None:
    with pytest.raises(ValidationError):
        ModelData.model_validate({**model_data, "rp_rs": measurement})


def test_stellar_source_cannot_be_empty(model_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ModelData.model_validate({**model_data, "stellar_source": ""})


def test_planet_radius_may_be_null_together_with_source(model_data: dict[str, Any]) -> None:
    data = {**model_data, "planet_radius_rearth": None, "stellar_source": None}
    assert ModelData.model_validate(data).planet_radius_rearth is None


@pytest.mark.parametrize("overrides", [{"planet_radius_rearth": None}, {"stellar_source": None}])
def test_planet_radius_and_source_go_together(
    model_data: dict[str, Any], overrides: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError, match="both"):
        ModelData.model_validate({**model_data, **overrides})
