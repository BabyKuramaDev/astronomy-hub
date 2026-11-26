"""model.json, written by `modeling`."""

from typing import Literal, Self

from pydantic import NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr

FitMethod = Literal["quick", "mcmc"]


class Measurement(ContractModel):
    """A value with asymmetric errors: the interval is [value - err_lower, value + err_upper]."""

    value: float
    err_lower: NonNegativeFloat
    err_upper: NonNegativeFloat

    @property
    def lower(self) -> float:
        return self.value - self.err_lower

    @property
    def upper(self) -> float:
        return self.value + self.err_upper


class McmcConvergence(ContractModel):
    walkers: PositiveInt
    steps: PositiveInt
    burn: NonNegativeInt
    seed: NonNegativeInt
    tau_max: PositiveFloat | None
    n_post_burn: PositiveInt
    autocorr_factor: PositiveFloat
    converged: bool
    acceptance_mean: NonNegativeFloat
    acceptance_min: NonNegativeFloat


class ModelData(ContractModel):
    # quick: least squares with covariance errors; mcmc: emcee posterior percentiles.
    method: FitMethod
    rp_rs: Measurement
    # Null when star.json has no stellar radius with its error; stellar_source goes with it.
    planet_radius_rearth: Measurement | None
    impact_parameter: Measurement
    a_rs: Measurement
    period_days: Measurement
    epoch_btjd: Measurement  # a mid-transit time near the middle of the data
    duration_hours: Measurement  # total duration T14, derived from the parameters
    jitter_ppm: Measurement  # white noise added in quadrature to every point's error
    stellar_source: NonEmptyStr | None
    convergence: McmcConvergence | None  # only with method=mcmc

    @model_validator(mode="after")
    def _consistency(self) -> Self:
        if (self.planet_radius_rearth is None) != (self.stellar_source is None):
            raise ValueError("planet_radius_rearth and stellar_source must be both set or null")
        if (self.method == "mcmc") != (self.convergence is not None):
            raise ValueError("convergence is set exactly when method is 'mcmc'")
        return self
