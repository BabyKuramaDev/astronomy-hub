"""folds/<tag>.json, written by `detection` (fold)."""

from typing import Literal, Self

from pydantic import NonNegativeFloat, NonNegativeInt, PositiveFloat, model_validator

from shared.contracts._base import ContractModel, PeakId, RelPath


class FoldBin(ContractModel):
    phase_hours: float
    depth_ppm: float | None
    depth_err_ppm: NonNegativeFloat | None
    n_points: NonNegativeInt


class OddEven(ContractModel):
    """Mean depth of odd and even transits; errors come from transit-to-transit scatter."""

    depth_odd_ppm: float | None
    depth_odd_err_ppm: NonNegativeFloat | None
    depth_even_ppm: float | None
    depth_even_err_ppm: NonNegativeFloat | None
    difference_ppm: float | None
    difference_sigma: NonNegativeFloat | None
    n_odd: NonNegativeInt  # number of odd transits measured
    n_even: NonNegativeInt


class FoldData(ContractModel):
    source: Literal["peak", "manual"]
    peak_id: PeakId | None
    period_days: PositiveFloat
    epoch_btjd: float
    duration_hours: PositiveFloat
    n_points: NonNegativeInt
    n_transits_covered: NonNegativeInt
    in_transit_depth_ppm: float | None
    oot_scatter_ppm: NonNegativeFloat | None
    bins: list[FoldBin]
    odd_even: OddEven
    data_file: RelPath
    figure_file: RelPath

    @model_validator(mode="after")
    def _peak_id_matches_source(self) -> Self:
        if (self.source == "peak") != (self.peak_id is not None):
            raise ValueError("peak_id is set exactly when source is 'peak'")
        return self
