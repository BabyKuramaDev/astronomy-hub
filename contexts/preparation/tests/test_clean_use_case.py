from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from contexts.preparation.application.clean import CLEAN, Clean, check_clean_table
from shared.contracts import LightcurveSetData, SectorLightcurve
from shared.kernel.contexts import Context
from shared.mission import load_mission
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import DataNotAvailableError
from shared.toolkit.meta import ToolMeta
from tests.support.synthetic import light_curve

CONFIG = load_mission("exoplanets").preparation


def meta(context: Context, tool: str) -> ToolMeta:
    return ToolMeta(
        context, tool, 99, "exoplanets", "0.1.0", lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )


def write_manifest(root: Path, sectors: dict[int, int]) -> None:
    """sectors: sector -> number of days of data (0 = no valid cadences)."""
    dossier = Dossier(root)
    entries = []
    for sector, days in sectors.items():
        table = f"lightcurve/s{sector:04d}.parquet"
        if days:
            time, flux, err = light_curve(start=1000.0 + 30 * sector, days=days, seed=sector)
        else:
            time = flux = err = np.array([], dtype=np.float64)
        dossier.write_table(table, {"time_btjd": time, "flux": flux, "flux_err": err})
        entries.append(
            SectorLightcurve(
                sector=sector,
                fits_file=f"lightcurve/s{sector}.fits",
                table_file=table,
                n_cadences=max(time.size, 1),
                n_valid=time.size,
                t_start_btjd=float(time[0]) if days else 0.0,
                t_end_btjd=float(time[-1]) if days else 0.0,
            )
        )
    data = LightcurveSetData(
        author="SPOC",
        exptime_s=120.0,
        flux_column="PDCSAP_FLUX",
        available_sectors=sorted(sectors),
        selection_rule="longest_consecutive_run",
        max_sectors=4,
        sectors=entries,
    )
    env = meta(Context.ACQUISITION, "fetch-lightcurves").envelope(data, {})
    dossier.write_envelope("lightcurve/manifest.json", env)


def test_clean_writes_table_and_records_inputs(tmp_path: Path) -> None:
    write_manifest(tmp_path, {2: 3, 3: 3, 4: 0})
    dossier = Dossier(tmp_path)
    summary = Clean(dossier, meta(Context.PREPARATION, "clean"), CONFIG).execute()
    assert summary["sectors"] == [2, 3]
    assert set(dossier.reads) == {
        "lightcurve/manifest.json",
        "lightcurve/s0002.parquet",
        "lightcurve/s0003.parquet",
    }
    table = Dossier(tmp_path).read_table(CLEAN)
    assert tuple(table) == ("time_btjd", "flux", "flux_err", "sector")
    assert table["time_btjd"].size == summary["n_points"]


def test_clean_without_valid_data(tmp_path: Path) -> None:
    write_manifest(tmp_path, {2: 0})
    with pytest.raises(DataNotAvailableError):
        Clean(Dossier(tmp_path), meta(Context.PREPARATION, "clean"), CONFIG).execute()


def test_clean_without_manifest(tmp_path: Path) -> None:
    with pytest.raises(DataNotAvailableError, match="manifest"):
        Clean(Dossier(tmp_path), meta(Context.PREPARATION, "clean"), CONFIG).execute()


@pytest.mark.parametrize(
    "columns",
    [
        {
            "time_btjd": np.array([2.0, 1.0]),
            "flux": np.ones(2),
            "flux_err": np.ones(2),
            "sector": np.ones(2),
        },
        {
            "time_btjd": np.array([1.0, 2.0]),
            "flux": np.array([1.0, np.nan]),
            "flux_err": np.ones(2),
            "sector": np.ones(2),
        },
        {
            "time_btjd": np.array([1.0, 2.0]),
            "flux": np.ones(2),
            "flux_err": np.zeros(2),
            "sector": np.ones(2),
        },
        {"flux": np.ones(2), "time_btjd": np.ones(2), "flux_err": np.ones(2), "sector": np.ones(2)},
    ],
)
def test_clean_table_contract(columns: dict[str, np.ndarray]) -> None:
    with pytest.raises(ValueError, match=r"time_btjd|flux|columns"):
        check_clean_table(columns)
