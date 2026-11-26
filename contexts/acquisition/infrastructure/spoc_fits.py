"""Read a SPOC light curve FITS file."""

from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

from contexts.acquisition.domain.lightcurve import SectorLightcurveRaw
from shared.toolkit.errors import InvalidInputError

CENTROID_COL, CENTROID_ROW = "MOM_CENTR1", "MOM_CENTR2"


def _column(table: Any, names: set[str], name: str, n: int) -> np.ndarray:
    """A float column, or NaN when the file does not have it (centroids are optional)."""
    if name not in names:
        return np.full(n, np.nan)
    return np.array(table[name], dtype=np.float64)


class SpocFitsReader:
    def read(self, path: Path, flux_column: str) -> SectorLightcurveRaw:
        try:
            with fits.open(path, memmap=False) as hdul:
                header = hdul[0].header
                table = hdul[1].data
                names = set(hdul[1].columns.names)
                n = len(table)
                return SectorLightcurveRaw(
                    sector=int(header["SECTOR"]),
                    tic_id=int(header["TICID"]),
                    time_btjd=np.array(table["TIME"], dtype=np.float64),
                    flux=np.array(table[flux_column], dtype=np.float64),
                    flux_err=np.array(table[f"{flux_column}_ERR"], dtype=np.float64),
                    quality=np.array(table["QUALITY"], dtype=np.int64),
                    centroid_col=_column(table, names, CENTROID_COL, n),
                    centroid_row=_column(table, names, CENTROID_ROW, n),
                )
        except (OSError, KeyError, IndexError) as exc:
            raise InvalidInputError(f"{path.name} is not a SPOC light curve: {exc}") from exc
