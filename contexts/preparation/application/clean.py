"""Use case: clean."""

from dataclasses import dataclass
from typing import Any

import numpy as np

from contexts.preparation.domain.cleaning import SectorSeries, clean_sectors, robust_std
from shared.contracts import CLEAN_TABLE_COLUMNS, LightcurveSetFile
from shared.mission import PreparationConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import DataNotAvailableError
from shared.toolkit.meta import ToolMeta

MANIFEST = "lightcurve/manifest.json"
CLEAN = "lightcurve_clean.parquet"


def check_clean_table(columns: dict[str, np.ndarray]) -> None:
    """The lightcurve_clean.parquet contract: fixed columns, finite values, sorted time."""
    if tuple(columns) != CLEAN_TABLE_COLUMNS:
        raise ValueError(f"columns must be {CLEAN_TABLE_COLUMNS}, got {tuple(columns)}")
    sizes = {values.size for values in columns.values()}
    if len(sizes) != 1:
        raise ValueError("columns have different lengths")
    for name in ("time_btjd", "flux", "flux_err"):
        if not np.isfinite(columns[name]).all():
            raise ValueError(f"{name} has non-finite values")
    if np.any(np.diff(columns["time_btjd"]) < 0):
        raise ValueError("time_btjd is not sorted")
    if np.any(columns["flux_err"] <= 0):
        raise ValueError("flux_err must be positive")


@dataclass
class Clean:
    dossier: Dossier
    meta: ToolMeta
    config: PreparationConfig

    def execute(self) -> dict[str, Any]:
        manifest = self.dossier.read_envelope(MANIFEST, LightcurveSetFile)
        series = []
        for entry in manifest.data.sectors:
            if entry.n_valid == 0:
                continue
            table = self.dossier.read_table(entry.table_file)
            series.append(
                SectorSeries(entry.sector, table["time_btjd"], table["flux"], table["flux_err"])
            )
        if not series:
            raise DataNotAvailableError("no valid cadences in any sector")
        result = clean_sectors(
            series,
            window_days=self.config.window_days,
            break_tolerance_days=self.config.break_tolerance_days,
            sigma_upper=self.config.sigma_upper,
        )
        if result.time_btjd.size == 0:
            raise DataNotAvailableError("no points left after cleaning")
        columns = {
            "time_btjd": result.time_btjd,
            "flux": result.flux,
            "flux_err": result.flux_err,
            "sector": result.sector,
        }
        check_clean_table(columns)
        self.dossier.write_table(CLEAN, columns)
        return {
            "tic_id": self.meta.tic_id,
            "n_points": int(result.time_btjd.size),
            "sectors": [s.sector for s in result.stats],
            "clipped": {str(s.sector): s.n_clipped for s in result.stats},
            "baseline_days": round(float(result.time_btjd[-1] - result.time_btjd[0]), 3),
            "rms_ppm": round(robust_std(result.flux) * 1e6, 1),
            "file": CLEAN,
        }
