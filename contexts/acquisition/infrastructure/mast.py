"""MAST adapters (astroquery): SPOC light curves and the TIC catalog.

Callers run inside shared.toolkit.caches.isolated_caches, so astroquery and
astropy never write to global caches.
"""

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from shared.toolkit.errors import DataNotAvailableError

LC_SUFFIX = "_lc.fits"


def _row_to_dict(row: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in row.colnames:
        value = row[name]
        if np.ma.is_masked(value):
            out[name] = None
        elif isinstance(value, np.generic):
            item = value.item()
            out[name] = None if isinstance(item, float) and math.isnan(item) else item
        else:
            out[name] = value
    return out


def _wrap_remote(action: str, exc: Exception) -> DataNotAvailableError:
    return DataNotAvailableError(f"MAST {action} failed: {type(exc).__name__}: {exc}")


class MastLightcurveArchive:
    def _observations(self, tic_id: int, author: str, exptime_s: float) -> Any:
        from astroquery.mast import Observations

        try:
            return Observations.query_criteria(
                target_name=str(tic_id),
                obs_collection="TESS",
                dataproduct_type="timeseries",
                provenance_name=author,
                t_exptime=[exptime_s - 1, exptime_s + 1],
            )
        except Exception as exc:
            raise _wrap_remote("observation query", exc) from exc

    def available_sectors(self, tic_id: int, author: str, exptime_s: float) -> list[int]:
        obs = self._observations(tic_id, author, exptime_s)
        return sorted({int(s) for s in obs["sequence_number"]}) if len(obs) else []

    def download(
        self, tic_id: int, sectors: Sequence[int], author: str, exptime_s: float, dest: Path
    ) -> dict[int, Path]:
        from astroquery.mast import Observations

        obs = self._observations(tic_id, author, exptime_s)
        wanted = {int(row["obsid"]): int(row["sequence_number"]) for row in obs}
        wanted = {obsid: s for obsid, s in wanted.items() if s in set(sectors)}
        if not wanted:
            return {}
        try:
            products = Observations.get_product_list(obs[np.isin(obs["obsid"], list(wanted))])
        except Exception as exc:
            raise _wrap_remote("product list", exc) from exc
        dest.mkdir(parents=True, exist_ok=True)
        files: dict[int, Path] = {}
        for row in products:
            name = str(row["productFilename"])
            if row["productSubGroupDescription"] != "LC" or not name.endswith(LC_SUFFIX):
                continue
            sector = wanted.get(int(row["parent_obsid"]))
            if sector is None or sector in files:
                continue
            target = dest / name
            if not target.exists():
                try:
                    Observations.download_products(
                        products[products["productFilename"] == name],
                        download_dir=str(dest),
                        flat=True,
                        cache=True,
                        verbose=False,
                    )
                except Exception as exc:
                    raise _wrap_remote(f"download of {name}", exc) from exc
            if not target.exists():
                raise DataNotAvailableError(f"MAST download of {name} produced no file")
            files[sector] = target
        return files


class MastTicCatalog:
    def target(self, tic_id: int) -> Mapping[str, Any]:
        from astroquery.mast import Catalogs

        try:
            rows = Catalogs.query_criteria(catalog="Tic", ID=tic_id)
        except Exception as exc:
            raise _wrap_remote("TIC query", exc) from exc
        if len(rows) != 1:
            raise DataNotAvailableError(f"TIC {tic_id}: expected one catalog row, got {len(rows)}")
        return _row_to_dict(rows[0])

    def neighbors(
        self, ra_deg: float, dec_deg: float, radius_arcsec: float
    ) -> list[Mapping[str, Any]]:
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astroquery.mast import Catalogs

        try:
            rows = Catalogs.query_region(
                SkyCoord(ra_deg, dec_deg, unit="deg"),
                radius=radius_arcsec * u.arcsec,
                catalog="Tic",
            )
        except Exception as exc:
            raise _wrap_remote("TIC cone search", exc) from exc
        return [_row_to_dict(row) for row in rows]

    def source(self, target: Mapping[str, Any]) -> str:
        version = target.get("version")
        return f"MAST TIC (version {version})" if version else "MAST TIC"
