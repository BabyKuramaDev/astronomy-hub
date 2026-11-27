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


FitStatus = Literal["fitted", "failed"]
MEASURED = (
    "rp_rs",
    "impact_parameter",
    "a_rs",
    "period_days",
    "epoch_btjd",
    "duration_hours",
    "jitter_ppm",
)


class ModelData(ContractModel):
    # quick: least squares with covariance errors; mcmc: emcee posterior percentiles.
    method: FitMethod
    # failed: the fit did not converge, left no valid samples or ended on an impossible
    # geometry (orbit inside the star, or b >= a/R* so nothing transits). A failed fit is a
    # result with its reason, every measurement null; it is not a tool error.
    status: FitStatus = "fitted"
    failure: NonEmptyStr | None = None
    rp_rs: Measurement | None
    # Null when star.json has no stellar radius with its error; stellar_source goes with it.
    planet_radius_rearth: Measurement | None
    impact_parameter: Measurement | None
    a_rs: Measurement | None
    period_days: Measurement | None
    epoch_btjd: Measurement | None  # a mid-transit time near the middle of the data
    duration_hours: Measurement | None  # total duration T14, derived from the parameters
    jitter_ppm: Measurement | None  # white noise added in quadrature to every point's error
    stellar_source: NonEmptyStr | None
    convergence: McmcConvergence | None  # only with method=mcmc

    @model_validator(mode="after")
    def _consistency(self) -> Self:
        if (self.planet_radius_rearth is None) != (self.stellar_source is None):
            raise ValueError("planet_radius_rearth and stellar_source must be both set or null")
        measured = [getattr(self, f) is not None for f in MEASURED]
        if self.status == "fitted":
            if not all(measured) or self.failure is not None:
                raise ValueError("a fitted model has every measurement and no failure")
            if (self.method == "mcmc") != (self.convergence is not None):
                raise ValueError("convergence is set exactly when method is 'mcmc'")
        else:
            if self.failure is None or any(measured) or self.planet_radius_rearth is not None:
                raise ValueError("a failed model has a failure reason and no measurement")
            if self.convergence is not None:
                raise ValueError("a failed model has no convergence")
        return self
