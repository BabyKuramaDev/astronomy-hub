"""A raw SPOC light curve of one sector and its quality filter."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SectorLightcurveRaw:
    sector: int
    tic_id: int
    time_btjd: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    quality: np.ndarray

    @property
    def n_cadences(self) -> int:
        return int(self.time_btjd.size)


def valid_mask(lc: SectorLightcurveRaw) -> np.ndarray:
    """Keep cadences with finite time, flux and error, and QUALITY == 0."""
    return (
        np.isfinite(lc.time_btjd)
        & np.isfinite(lc.flux)
        & np.isfinite(lc.flux_err)
        & (lc.quality == 0)
    )
