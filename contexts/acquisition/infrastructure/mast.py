"""MAST adapters (astroquery): SPOC light curves and the TIC catalog.

Callers run inside shared.toolkit.caches.isolated_caches, so astroquery and
astropy never write to global caches.
"""

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from shared.toolkit.errors import DataNotAvailableError, ServiceUnavailableError
from shared.toolkit.retry import DeadlineExceededError, RetryPolicy, is_transient

LC_SUFFIX = "_lc.fits"
# Single-sector SPOC light curve observations, for example
# tess2018234235059-s0002-0000000100100827-0121-s. Multi-sector Data Validation
# observations (tess2018206190142-s0001-s0036-...) carry the last sector as their
# sequence_number but have no light curve, so they are excluded.
SINGLE_SECTOR_OBS_ID = re.compile(r"^tess\d{13}-s(?P<sector>\d{4})-\d{16}-\d{4}-s$")


def single_sector_rows(obs: Any) -> list[Any]:
    rows = []
    for row in obs:
        match = SINGLE_SECTOR_OBS_ID.match(str(row["obs_id"]))
        if match and int(match["sector"]) == int(row["sequence_number"]):
            rows.append(row)
    return rows


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


def _wrap_remote(action: str, exc: Exception) -> Exception:
    """MAST failed or did not answer in time (a transient error, or the policy's deadline):
    ServiceUnavailableError, unlike data that does not exist. Any other error, a bug for
    example, is returned unchanged so that it is never disguised as an outage."""
    if not (is_transient(exc) or isinstance(exc, DeadlineExceededError)):
        return exc
    return ServiceUnavailableError(
        f"MAST unavailable: {action} failed: {type(exc).__name__}: {exc}; rerun the tool once"
    )


def _timed[T](retry: RetryPolicy, call: Any) -> T:
    """Run an astroquery MAST call with the policy's per-request timeout."""
    from astroquery.mast import conf

    timeout = retry.timeout_s()
    if timeout is None:
        return call()
    with conf.set_temp("timeout", math.ceil(timeout)):  # astroquery wants whole seconds
        return call()


class MastLightcurveArchive:
    """Every remote call is retried on transient errors (see shared.toolkit.retry)."""

    def __init__(self, retry: RetryPolicy | None = None) -> None:
        self.retry = retry or RetryPolicy()

    def _observations(self, tic_id: int, author: str, exptime_s: float) -> Any:
        from astroquery.mast import Observations

        try:
            return self.retry.call(
                lambda: _timed(
                    self.retry,
                    lambda: Observations.query_criteria(
                        target_name=str(tic_id),
                        obs_collection="TESS",
                        dataproduct_type="timeseries",
                        provenance_name=author,
                        t_exptime=[exptime_s - 1, exptime_s + 1],
                    ),
                )
            )
        except Exception as exc:
            wrapped = _wrap_remote("observation query", exc)
            if wrapped is exc:
                raise
            raise wrapped from exc

    def available_sectors(self, tic_id: int, author: str, exptime_s: float) -> list[int]:
        obs = self._observations(tic_id, author, exptime_s)
        return sorted({int(row["sequence_number"]) for row in single_sector_rows(obs)})

    def download(
        self, tic_id: int, sectors: Sequence[int], author: str, exptime_s: float, dest: Path
    ) -> dict[int, Path]:
        from astroquery.mast import Observations

        obs = self._observations(tic_id, author, exptime_s)
        wanted = {
            int(row["obsid"]): int(row["sequence_number"])
            for row in single_sector_rows(obs)
            if int(row["sequence_number"]) in set(sectors)
        }
        if not wanted:
            return {}
        try:
            mask = np.array([int(obsid) in wanted for obsid in obs["obsid"]])
            products = self.retry.call(
                lambda: _timed(self.retry, lambda: Observations.get_product_list(obs[mask]))
            )
        except Exception as exc:
            wrapped = _wrap_remote("product list", exc)
            if wrapped is exc:
                raise
            raise wrapped from exc
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
                selection = products[products["productFilename"] == name]
                try:
                    self.retry.call(
                        lambda selection=selection: _timed(
                            self.retry,
                            lambda: Observations.download_products(
                                selection,
                                download_dir=str(dest),
                                flat=True,
                                cache=True,
                                verbose=False,
                            ),
                        )
                    )
                except Exception as exc:
                    wrapped = _wrap_remote(f"download of {name}", exc)
                    if wrapped is exc:
                        raise
                    raise wrapped from exc
            if not target.exists():
                raise DataNotAvailableError(f"MAST download of {name} produced no file")
            files[sector] = target
        return files


class MastTicCatalog:
    def __init__(self, retry: RetryPolicy | None = None) -> None:
        self.retry = retry or RetryPolicy()

    def target(self, tic_id: int) -> Mapping[str, Any]:
        from astroquery.mast import Catalogs

        try:
            rows = self.retry.call(
                lambda: _timed(
                    self.retry, lambda: Catalogs.query_criteria(catalog="Tic", ID=tic_id)
                )
            )
        except Exception as exc:
            wrapped = _wrap_remote("TIC query", exc)
            if wrapped is exc:
                raise
            raise wrapped from exc
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
            rows = self.retry.call(
                lambda: _timed(
                    self.retry,
                    lambda: Catalogs.query_region(
                        SkyCoord(ra_deg, dec_deg, unit="deg"),
                        radius=radius_arcsec * u.arcsec,
                        catalog="Tic",
                    ),
                )
            )
        except Exception as exc:
            wrapped = _wrap_remote("TIC cone search", exc)
            if wrapped is exc:
                raise
            raise wrapped from exc
        return [_row_to_dict(row) for row in rows]

    def source(self, target: Mapping[str, Any]) -> str:
        version = target.get("version")
        return f"MAST TIC (version {version})" if version else "MAST TIC"
