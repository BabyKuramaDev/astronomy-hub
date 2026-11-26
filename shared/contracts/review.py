"""review/reproduction.json and review.json, written by `review`."""

from typing import Annotated, Literal, Self

from pydantic import Field, NonNegativeFloat, PositiveFloat, PositiveInt, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr

ReviewVerdict = Literal["reproduced", "partial", "not_reproduced"]

# Required when detected=true, null when detected=false.
REPRODUCTION_FIELDS = ("period_days", "epoch_btjd", "duration_hours", "depth_ppm", "sde", "snr")


class ReproductionData(ContractModel):
    """The independent analysis: other cleaning, other search, never signal.json."""

    detrend_method: NonEmptyStr
    detrend_window_days: PositiveFloat
    search_method: NonEmptyStr
    sectors: Annotated[list[PositiveInt], Field(min_length=1)]
    period_min_days: PositiveFloat
    period_max_days: PositiveFloat
    detected: bool  # the best peak reaches sde_min
    sde_min: PositiveFloat
    period_days: PositiveFloat | None
    epoch_btjd: float | None
    duration_hours: PositiveFloat | None
    depth_ppm: float | None
    sde: float | None
    snr: float | None
    n_transits: int | None

    @model_validator(mode="after")
    def _fields_match_detected(self) -> Self:
        values = {name: getattr(self, name) for name in REPRODUCTION_FIELDS}
        if self.detected and None in values.values():
            missing = [k for k, v in values.items() if v is None]
            raise ValueError(f"detected=true requires {', '.join(missing)}")
        return self


class ReviewData(ContractModel):
    period_days_independent: PositiveFloat | None
    depth_ppm_independent: PositiveFloat | None
    disagreements: list[NonEmptyStr]
    verdict: ReviewVerdict
    period_ratio: NonNegativeFloat | None  # independent / signal period
    depth_ratio: NonNegativeFloat | None  # independent / signal depth
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def _reproduced_has_independent_values(self) -> Self:
        if self.verdict == "reproduced" and (
            self.period_days_independent is None or self.depth_ppm_independent is None
        ):
            raise ValueError("verdict=reproduced requires independent period and depth")
        return self
