from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from contexts.acquisition.application.fetch_lightcurves import MANIFEST, FetchLightcurves
from contexts.acquisition.application.fetch_star import STAR, FetchStar
from contexts.acquisition.infrastructure.spoc_fits import SpocFitsReader
from shared.contracts import LightcurveSetFile, StarFile
from shared.kernel.contexts import Context
from shared.mission import load_mission
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import DataNotAvailableError, InvalidInputError
from shared.toolkit.meta import ToolMeta
from tests.support.synthetic import light_curve, write_spoc_fits

TIC = 4242
CONFIG = load_mission("exoplanets").acquisition


def meta(tool: str) -> ToolMeta:
    return ToolMeta(
        Context.ACQUISITION,
        tool,
        TIC,
        "exoplanets",
        "0.1.0",
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeArchive:
    def __init__(self, sectors: list[int], tic_in_file: int = TIC) -> None:
        self.sectors = sectors
        self.tic_in_file = tic_in_file
        self.downloads: list[int] = []

    def available_sectors(self, tic_id: int, author: str, exptime_s: float) -> list[int]:
        return self.sectors

    def download(
        self, tic_id: int, sectors: Sequence[int], author: str, exptime_s: float, dest: Path
    ) -> dict[int, Path]:
        files = {}
        for sector in sectors:
            path = dest / f"tess-s{sector:04d}-{tic_id:016d}_lc.fits"
            if not path.exists():
                self.downloads.append(sector)
                time, flux, err = light_curve(start=1000.0 + 27 * sector, days=2.0, seed=sector)
                quality = np.zeros(time.size, dtype=np.int32)
                quality[:10] = 1
                flux[10:15] = np.nan
                write_spoc_fits(
                    path,
                    tic_id=self.tic_in_file,
                    sector=sector,
                    time=time,
                    flux=flux,
                    flux_err=err,
                    quality=quality,
                )
            files[sector] = path
        return files


def test_fetch_lightcurves_writes_tables_and_manifest(tmp_path: Path) -> None:
    archive = FakeArchive([2, 3, 4, 29, 30, 31, 32, 69])
    dossier = Dossier(tmp_path)
    summary = FetchLightcurves(
        archive, SpocFitsReader(), dossier, meta("fetch-lightcurves"), CONFIG
    ).execute()
    assert summary["sectors"] == [29, 30, 31, 32]
    manifest = Dossier(tmp_path).read_envelope(MANIFEST, LightcurveSetFile)
    first = manifest.data.sectors[0]
    assert first.n_valid == first.n_cadences - 15
    assert set(manifest.inputs) == {s.fits_file for s in manifest.data.sectors}
    table = Dossier(tmp_path).read_table(first.table_file)
    assert table["time_btjd"].size == first.n_valid
    assert np.isfinite(table["flux"]).all()
    assert MANIFEST in dossier.writes
    assert first.fits_file in dossier.writes


def test_fetch_lightcurves_is_idempotent(tmp_path: Path) -> None:
    archive = FakeArchive([2, 3])
    first = Dossier(tmp_path)
    FetchLightcurves(archive, SpocFitsReader(), first, meta("fetch-lightcurves"), CONFIG).execute()
    second = Dossier(tmp_path)
    FetchLightcurves(archive, SpocFitsReader(), second, meta("fetch-lightcurves"), CONFIG).execute()
    assert archive.downloads == [2, 3]
    assert first.writes == second.writes


def test_no_light_curves_is_data_not_available(tmp_path: Path) -> None:
    with pytest.raises(DataNotAvailableError, match="SPOC"):
        FetchLightcurves(
            FakeArchive([]), SpocFitsReader(), Dossier(tmp_path), meta("fetch-lightcurves"), CONFIG
        ).execute()


def test_file_of_another_star_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="expected TIC"):
        FetchLightcurves(
            FakeArchive([2], tic_in_file=1), SpocFitsReader(), Dossier(tmp_path), meta("x"), CONFIG
        ).execute()


class FakeCatalog:
    def target(self, tic_id: int) -> Mapping[str, Any]:
        return {"ID": tic_id, "ra": 10.0, "dec": -5.0, "Tmag": 9.0, "rad": 1.1, "e_rad": 0.1}

    def neighbors(self, ra: float, dec: float, radius: float) -> list[Mapping[str, Any]]:
        return [
            {"ID": TIC, "dstArcSec": 0.0, "Tmag": 9.0},
            {"ID": 7, "dstArcSec": 20.0, "Tmag": 13.0},
        ]

    def source(self, target: Mapping[str, Any]) -> str:
        return "fake TIC"


def test_fetch_star_writes_star_json(tmp_path: Path) -> None:
    summary = FetchStar(FakeCatalog(), Dossier(tmp_path), meta("fetch-star"), CONFIG).execute()
    assert summary["n_neighbors"] == 1
    assert summary["radius_rsun"] == pytest.approx(1.1)
    star = Dossier(tmp_path).read_envelope(STAR, StarFile)
    assert star.data.neighbors[0].tic_id == 7
