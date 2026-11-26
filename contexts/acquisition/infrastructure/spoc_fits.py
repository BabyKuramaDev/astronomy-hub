"""Read a SPOC light curve FITS file."""

from pathlib import Path

import numpy as np
from astropy.io import fits

from contexts.acquisition.domain.lightcurve import SectorLightcurveRaw
from shared.toolkit.errors import InvalidInputError


class SpocFitsReader:
    def read(self, path: Path, flux_column: str) -> SectorLightcurveRaw:
        try:
            with fits.open(path, memmap=False) as hdul:
                header = hdul[0].header
                table = hdul[1].data
                return SectorLightcurveRaw(
                    sector=int(header["SECTOR"]),
                    tic_id=int(header["TICID"]),
                    time_btjd=np.array(table["TIME"], dtype=np.float64),
                    flux=np.array(table[flux_column], dtype=np.float64),
                    flux_err=np.array(table[f"{flux_column}_ERR"], dtype=np.float64),
                    quality=np.array(table["QUALITY"], dtype=np.int64),
                )
        except (OSError, KeyError, IndexError) as exc:
            raise InvalidInputError(f"{path.name} is not a SPOC light curve: {exc}") from exc
