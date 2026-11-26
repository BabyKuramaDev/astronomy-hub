"""search.json, written by `detection` (search-period)."""

from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    StringConstraints,
    model_validator,
)

from shared.contracts._base import ContractModel, NonEmptyStr, PeakId

Ratio = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*/[1-9][0-9]*$")]


class SearchPeak(ContractModel):
    id: PeakId
    period_days: PositiveFloat
    epoch_btjd: float
    duration_hours: PositiveFloat
    depth_ppm: PositiveFloat
    snr: NonNegativeFloat
    n_transits: PositiveInt
    power: float


class DiscardedPeak(ContractModel):
    period_days: PositiveFloat
    epoch_btjd: float
    duration_hours: PositiveFloat
    depth_ppm: float
    snr: float
    power: float
    reason: Literal["non_positive_depth", "harmonic"]
    harmonic_of: PeakId | None
    # period / period of the kept peak, as an integer fraction such as "2/1" or "1/2".
    ratio: Ratio | None

    @model_validator(mode="after")
    def _reason_matches_fields(self) -> Self:
        if self.reason == "harmonic" and (self.harmonic_of is None or self.ratio is None):
            raise ValueError("a harmonic needs harmonic_of and ratio")
        if self.reason == "non_positive_depth":
            if self.depth_ppm > 0:
                raise ValueError("non_positive_depth requires depth_ppm <= 0")
            if self.harmonic_of is not None or self.ratio is not None:
                raise ValueError("non_positive_depth has no harmonic_of or ratio")
        return self


class PeriodSearchData(ContractModel):
    method: NonEmptyStr
    sectors: Annotated[list[PositiveInt], Field(min_length=1)]
    period_min_days: PositiveFloat
    period_max_days: PositiveFloat
    durations_hours: Annotated[list[PositiveFloat], Field(min_length=1)]
    bin_minutes: PositiveFloat
    n_periods: PositiveInt
    peaks: list[SearchPeak]
    discarded: list[DiscardedPeak]

    @model_validator(mode="after")
    def _peaks_are_consistent(self) -> Self:
        if self.period_min_days >= self.period_max_days:
            raise ValueError("period_min_days must be below period_max_days")
        ids = [p.id for p in self.peaks]
        if ids != [f"p{i}" for i in range(1, len(ids) + 1)]:
            raise ValueError("peak ids must be p1, p2, ... in rank order")
        unknown = {d.harmonic_of for d in self.discarded if d.harmonic_of} - set(ids)
        if unknown:
            raise ValueError(f"harmonic_of refers to unknown peaks: {sorted(unknown)}")
        return self

    def peak(self, peak_id: str) -> SearchPeak | None:
        return next((p for p in self.peaks if p.id == peak_id), None)
