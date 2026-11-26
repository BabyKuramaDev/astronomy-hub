from pathlib import Path

import numpy as np
import pytest

from shared.toolkit.dossier import Dossier
from tests.support.synthetic import Transit, light_curve

TRANSIT = Transit(period_days=2.345, epoch_btjd=1000.7, duration_hours=2.5, depth_ppm=3000.0)


def write_clean(root: Path, time: np.ndarray, flux: np.ndarray, err: np.ndarray) -> None:
    sector = np.where(time < time.min() + 27.0, 2, 3).astype(np.int16)
    Dossier(root).write_table(
        "lightcurve_clean.parquet",
        {"time_btjd": time, "flux": flux, "flux_err": err, "sector": sector},
    )


@pytest.fixture
def clean_dossier(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    time, flux, err = light_curve(days=27.0, transit=TRANSIT, noise_ppm=1000.0, seed=2)
    write_clean(source, time, flux, err)
    return source
