"""star.json, written by `acquisition`."""

from typing import Annotated, Self

from pydantic import Field, NonNegativeFloat, PositiveFloat, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr, TicId
from shared.contracts.model import Measurement


class Neighbor(ContractModel):
    tic_id: TicId
    separation_arcsec: NonNegativeFloat
    tmag: float | None


class StarData(ContractModel):
    ra_deg: Annotated[float, Field(ge=0, lt=360)]
    dec_deg: Annotated[float, Field(ge=-90, le=90)]
    tmag: float | None
    # Each parameter is recorded only when the catalog gives the value with its error.
    teff_k: Measurement | None
    logg: Measurement | None
    radius_rsun: Measurement | None
    mass_msun: Measurement | None
    contamination_ratio: NonNegativeFloat | None
    source: NonEmptyStr
    neighbor_radius_arcsec: PositiveFloat
    neighbors: list[Neighbor]

    @model_validator(mode="after")
    def _neighbors_are_consistent(self) -> Self:
        seps = [n.separation_arcsec for n in self.neighbors]
        if seps != sorted(seps):
            raise ValueError("neighbors must be sorted by separation")
        if any(sep > self.neighbor_radius_arcsec for sep in seps):
            raise ValueError("neighbors must lie within neighbor_radius_arcsec")
        ids = [n.tic_id for n in self.neighbors]
        if len(set(ids)) != len(ids):
            raise ValueError("neighbor tic_ids must be unique")
        return self
