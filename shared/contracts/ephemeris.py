"""ephemeris.json, written by `followup`."""

from typing import Annotated, Self

from pydantic import Field, NonNegativeFloat, NonNegativeInt, PositiveFloat, model_validator

from shared.contracts._base import ContractModel, UtcDatetime
from shared.contracts.model import FitMethod, Measurement


class PredictedTransit(ContractModel):
    n: NonNegativeInt  # transits after the reference epoch
    mid_btjd: float
    mid_utc: UtcDatetime
    ingress_utc: UtcDatetime
    egress_utc: UtcDatetime
    err_minutes: NonNegativeFloat  # 1 sigma on the mid-transit time


class EphemerisData(ContractModel):
    model_method: FitMethod
    period_days: Measurement
    epoch_btjd: Measurement
    duration_hours: PositiveFloat
    start_utc: UtcDatetime
    horizon_days: PositiveFloat
    # Times are barycentric (BTJD = BJD_TDB - 2457000) shown in UTC; no correction for
    # the observer's position, which can shift them by up to about 8 minutes.
    transits: Annotated[list[PredictedTransit], Field(max_length=1000)]

    @model_validator(mode="after")
    def _transits_are_ordered(self) -> Self:
        numbers = [t.n for t in self.transits]
        if numbers != sorted(set(numbers)):
            raise ValueError("transits must be ordered by n without repeats")
        return self
