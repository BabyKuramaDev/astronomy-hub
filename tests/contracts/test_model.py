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
        "period_days": m(0.941452, 1e-6, 1e-6),
        "epoch_btjd": m(3000.5, 1e-4, 1e-4),
        "duration_hours": m(2.19, 0.02, 0.02),
        "jitter_ppm": m(120.0, 10.0, 10.0),
        "method": "quick",
        "stellar_source": "TIC v8.2",
        "convergence": None,
    }


CONVERGENCE = {
    "walkers": 32,
    "steps": 8000,
    "burn": 2000,
    "seed": 42,
    "tau_max": 103.0,
    "n_post_burn": 6000,
    "autocorr_factor": 50.0,
    "converged": True,
    "acceptance_mean": 0.35,
    "acceptance_min": 0.2,
}


def test_mcmc_needs_convergence(model_data: dict[str, Any]) -> None:
    ModelData.model_validate({**model_data, "method": "mcmc", "convergence": CONVERGENCE})
    with pytest.raises(ValidationError, match="convergence"):
        ModelData.model_validate({**model_data, "method": "mcmc"})
    with pytest.raises(ValidationError, match="convergence"):
        ModelData.model_validate({**model_data, "convergence": CONVERGENCE})


def test_measurement_bounds() -> None:
    m_ = Measurement(value=2.0, err_lower=0.5, err_upper=0.25)
    assert (m_.lower, m_.upper) == (1.5, 2.25)


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
