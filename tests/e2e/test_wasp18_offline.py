"""WASP-18 b through every M1 tool, offline: real (trimmed) SPOC files and TIC rows."""

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from contexts.acquisition.application.fetch_lightcurves import FetchLightcurves
from contexts.acquisition.application.fetch_star import FetchStar
from contexts.acquisition.infrastructure.spoc_fits import SpocFitsReader
from shared.contracts import LogEntry, ModelFile, SignalFile, StarFile
from shared.kernel.contexts import Context
from shared.mission import load_mission
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta
from tests.e2e.wasp18 import FIXTURES, detection_chain, reference

REF = reference()
TIC = REF["tic_id"]
MISSION = load_mission("exoplanets")


class FixtureArchive:
    def available_sectors(self, tic_id: int, author: str, exptime_s: float) -> list[int]:
        return [int(p.name[1:5]) for p in sorted(FIXTURES.glob("s*_trimmed.fits"))]

    def download(
        self, tic_id: int, sectors: Sequence[int], author: str, exptime_s: float, dest: Path
    ) -> dict[int, Path]:
        dest.mkdir(parents=True, exist_ok=True)
        files = {}
        for sector in sectors:
            target = dest / f"s{sector:04d}_trimmed.fits"
            target.write_bytes((FIXTURES / target.name).read_bytes())
            files[sector] = target
        return files


class FixtureCatalog:
    def target(self, tic_id: int) -> Mapping[str, Any]:
        return json.loads((FIXTURES / "tic_target.json").read_text())["row"]

    def neighbors(self, ra: float, dec: float, radius: float) -> list[Mapping[str, Any]]:
        return json.loads((FIXTURES / "tic_neighbors.json").read_text())["rows"]

    def source(self, target: Mapping[str, Any]) -> str:
        return f"MAST TIC (version {target['version']}), recorded fixture"


def meta(tool: str) -> ToolMeta:
    return ToolMeta(
        Context.ACQUISITION, tool, TIC, "exoplanets", "0.1.0", lambda: datetime.now(UTC)
    )


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    workspace = tmp_path_factory.mktemp("ws")
    dossier = Dossier.for_target(workspace, "exoplanets", TIC)
    FetchLightcurves(
        FixtureArchive(), SpocFitsReader(), dossier, meta("fetch-lightcurves"), MISSION.acquisition
    ).execute()
    FetchStar(FixtureCatalog(), dossier, meta("fetch-star"), MISSION.acquisition).execute()
    return dossier.root, detection_chain(TIC, workspace)


def test_period_within_one_percent_of_catalog(run: tuple[Path, dict[str, Any]]) -> None:
    root, _ = run
    signal = Dossier(root).read_envelope("signal.json", SignalFile).data
    assert signal.detected
    assert signal.period_days == pytest.approx(REF["period_days"], rel=0.01)


def test_fixtures_are_small() -> None:
    total = sum(p.stat().st_size for p in FIXTURES.iterdir() if p.is_file())
    assert total < 1_000_000


def test_star_and_model(run: tuple[Path, dict[str, Any]]) -> None:
    root, out = run
    star = Dossier(root).read_envelope("star.json", StarFile).data
    assert star.radius_rsun is not None
    model = Dossier(root).read_envelope("model.json", ModelFile).data
    assert model.planet_radius_rearth is not None
    assert model.stellar_source == star.source
    assert "convergence" in out["fit"]


def test_every_tool_logged(run: tuple[Path, dict[str, Any]]) -> None:
    root, _ = run
    entries = [
        LogEntry.model_validate_json(line) for line in (root / "log.jsonl").read_text().splitlines()
    ]
    assert [e.tool for e in entries] == [
        "clean",
        "search-period",
        "select-peak",
        "fold",
        "fit-transit",
    ]
    assert all(e.exit_code == 0 for e in entries)
    assert entries[2].reason
