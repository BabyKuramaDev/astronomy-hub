"""model.json, written by `modeling`."""

from typing import Self

from pydantic import NonNegativeFloat, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr


class Measurement(ContractModel):
    """A value with asymmetric errors: the interval is [value - err_lower, value + err_upper]."""

    value: float
    err_lower: NonNegativeFloat
    err_upper: NonNegativeFloat


class ModelData(ContractModel):
    rp_rs: Measurement
    # Null when star.json has no stellar radius with its error; stellar_source goes with it.
    planet_radius_rearth: Measurement | None
    impact_parameter: Measurement
    a_rs: Measurement
    stellar_source: NonEmptyStr | None

    @model_validator(mode="after")
    def _radius_and_source_go_together(self) -> Self:
        if (self.planet_radius_rearth is None) != (self.stellar_source is None):
            raise ValueError("planet_radius_rearth and stellar_source must be both set or null")
        return self
