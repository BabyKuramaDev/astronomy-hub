"""lightcurve/manifest.json, written by `acquisition`."""

from typing import Annotated, Literal, Self

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr, RelPath

# Columns of every per-sector table (lightcurve/sNNNN.parquet) and of lightcurve_clean.parquet.
# Per-sector tables keep the flux-weighted centroid (pixels) for vetting gate 8; it may be NaN.
SECTOR_TABLE_COLUMNS = ("time_btjd", "flux", "flux_err", "centroid_col", "centroid_row")
CLEAN_TABLE_COLUMNS = ("time_btjd", "flux", "flux_err", "sector")


class SectorLightcurve(ContractModel):
    sector: PositiveInt
    fits_file: RelPath
    table_file: RelPath
    n_cadences: NonNegativeInt
    n_valid: NonNegativeInt
    t_start_btjd: float
    t_end_btjd: float

    @model_validator(mode="after")
    def _counts_and_times(self) -> Self:
        if self.n_valid > self.n_cadences:
            raise ValueError("n_valid cannot exceed n_cadences")
        if self.t_end_btjd < self.t_start_btjd:
            raise ValueError("t_end_btjd must not precede t_start_btjd")
        return self


class LightcurveSetData(ContractModel):
    author: NonEmptyStr
    exptime_s: PositiveFloat
    flux_column: Literal["PDCSAP_FLUX"]
    available_sectors: list[PositiveInt]
    selection_rule: Literal["longest_consecutive_run"]
    max_sectors: PositiveInt
    sectors: Annotated[list[SectorLightcurve], Field(min_length=1)]

    @model_validator(mode="after")
    def _sectors_are_consistent(self) -> Self:
        if self.available_sectors != sorted(set(self.available_sectors)):
            raise ValueError("available_sectors must be sorted and unique")
        chosen = [s.sector for s in self.sectors]
        if chosen != sorted(set(chosen)):
            raise ValueError("sectors must be sorted and unique")
        if not set(chosen) <= set(self.available_sectors):
            raise ValueError("every chosen sector must be available")
        if len(chosen) > self.max_sectors:
            raise ValueError("more sectors than max_sectors")
        return self
