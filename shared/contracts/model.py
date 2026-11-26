"""model.json, written by `modeling`."""

from pydantic import NonNegativeFloat

from shared.contracts._base import ContractModel, NonEmptyStr


class Measurement(ContractModel):
    """A value with asymmetric errors: the interval is [value - err_lower, value + err_upper]."""

    value: float
    err_lower: NonNegativeFloat
    err_upper: NonNegativeFloat


class ModelData(ContractModel):
    rp_rs: Measurement
    planet_radius_rearth: Measurement
    impact_parameter: Measurement
    a_rs: Measurement
    stellar_source: NonEmptyStr
