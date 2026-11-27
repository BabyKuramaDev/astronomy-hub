"""M2 acceptance, offline: WASP-18 b's complete dossier without an LLM ends in candidate.

Acquisition reads the recorded (trimmed) SPOC files and TIC rows; scripts/build_dossier.py
then runs every other tool as a subprocess, in eval mode. A confirmed planet must never
come out false_positive. Catalog is checked apart with the recorded TAP and ExoFOP answers.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from contexts.acquisition.application.fetch_lightcurves import FetchLightcurves
from contexts.acquisition.application.fetch_star import FetchStar
from contexts.acquisition.infrastructure.spoc_fits import SpocFitsReader
from contexts.catalog.application.crossmatch import Crossmatch
from contexts.catalog.domain.crossmatch import CatalogEntry
from contexts.catalog.infrastructure.archive import parse_confirmed, parse_ctois, parse_tois
from shared.contracts import (
    CatalogFile,
    DecisionFile,
    LogEntry,
    ModelFile,
    ReviewFile,
    SignalFile,
    VettingFile,
)
from shared.kernel.contexts import Context
from shared.mission import load_mission
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta
from tests.e2e.wasp18 import FIXTURES, build_dossier, reference

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


class FixturePlanetCatalogs:
    """The TAP and ExoFOP answers recorded in catalogs.json."""

    def __init__(self) -> None:
        self.raw = json.loads((FIXTURES / "catalogs.json").read_text())

    def confirmed_planets(self, tic_id: int) -> list[CatalogEntry]:
        return parse_confirmed(self.raw["pscomppars"]["rows"])

    def tois(self, tic_id: int) -> list[CatalogEntry]:
        return parse_tois(self.raw["toi"]["rows"], tic_id)

    def ctois(self, tic_id: int) -> list[CatalogEntry]:
        return parse_ctois(self.raw["exofop"]["target"], tic_id)

    def describe(self) -> str:
        return "recorded fixture"


def meta(context: Context, tool: str) -> ToolMeta:
    return ToolMeta(context, tool, TIC, "exoplanets", "0.1.0", lambda: datetime.now(UTC))


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    workspace = tmp_path_factory.mktemp("ws")
    dossier = Dossier.for_target(workspace, "exoplanets", TIC)
    FetchLightcurves(
        FixtureArchive(),
        SpocFitsReader(),
        dossier,
        meta(Context.ACQUISITION, "fetch-lightcurves"),
        MISSION.acquisition,
    ).execute()
    FetchStar(
        FixtureCatalog(), dossier, meta(Context.ACQUISITION, "fetch-star"), MISSION.acquisition
    ).execute()
    summary = build_dossier(TIC, workspace, "--mode", "eval", "--skip", "acquisition,catalog")
    return dossier.root, summary


def test_eval_mode_ends_in_candidate(run: tuple[Path, dict[str, Any]]) -> None:
    root, summary = run
    decision = Dossier(root).read_envelope("decision.json", DecisionFile).data
    assert decision.mode == "eval"
    assert decision.final == "candidate" == summary["final"]


def test_a_confirmed_planet_is_never_a_false_positive(run: tuple[Path, dict[str, Any]]) -> None:
    root, _ = run
    vetting = Dossier(root).read_envelope("vetting.json", VettingFile).data
    assert vetting.verdict != "false_positive"
    assert not [g.id for g in vetting.gates if g.severity == "hard" and g.status == "fail"]
    secondary = next(g for g in vetting.gates if g.id == "secondary")
    assert secondary.status == "pass"


def test_period_within_one_percent_of_catalog(run: tuple[Path, dict[str, Any]]) -> None:
    root, _ = run
    signal = Dossier(root).read_envelope("signal.json", SignalFile).data
    assert signal.detected
    assert signal.period_days == pytest.approx(REF["period_days"], rel=0.01)


def test_review_reproduces_and_eval_skips_the_mcmc(run: tuple[Path, dict[str, Any]]) -> None:
    root, _ = run
    assert Dossier(root).read_envelope("review.json", ReviewFile).data.verdict == "reproduced"
    model = Dossier(root).read_envelope("model.json", ModelFile).data
    assert model.method == "quick"  # eval metrics never use the MCMC
    assert model.planet_radius_rearth is not None


def test_eval_profile_ends_at_decide(run: tuple[Path, dict[str, Any]]) -> None:
    root, _ = run
    for name in ("report.md", "ephemeris.json", "catalog.json"):
        assert not (root / name).exists(), f"the eval profile writes no {name}"


def test_every_tool_logged_in_order(run: tuple[Path, dict[str, Any]]) -> None:
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
        "run-gates",
        "conclude",
        "reproduce",
        "conclude",
        "decide",
    ]
    assert all(e.exit_code == 0 for e in entries)
    assert entries[2].reason


def test_crossmatch_with_recorded_answers(run: tuple[Path, dict[str, Any]]) -> None:
    root, _ = run
    Crossmatch(
        FixturePlanetCatalogs(),
        Dossier(root),
        meta(Context.CATALOG, "crossmatch"),
        MISSION.catalog,
    ).execute()
    catalog = Dossier(root).read_envelope("catalog.json", CatalogFile).data
    assert catalog.status == "known_planet"
    assert all(m.period_match for m in catalog.matches)


def test_fixtures_are_small() -> None:
    total = sum(p.stat().st_size for p in FIXTURES.iterdir() if p.is_file())
    assert total < 1_000_000


@pytest.mark.parametrize("stage", ["select", "fit", "vetting", "review"])
def test_staged_rerun_gives_the_same_decision(
    run: tuple[Path, dict[str, Any]], tmp_path: Path, stage: str
) -> None:
    import shutil

    from evals.baseline import clear

    root, summary = run
    copy = tmp_path / "exoplanets" / str(TIC)
    shutil.copytree(root, copy)
    search = (copy / "search.json").read_bytes()
    clear(copy, stage)
    rerun = build_dossier(
        TIC, tmp_path, "--mode", "eval", "--skip", "acquisition,catalog", "--from", stage
    )
    assert rerun["final"] == summary["final"] == "candidate"
    assert (copy / "search.json").read_bytes() == search, "earlier stages are not rerun"
    tools = [s["tool"] for s in rerun["steps"]]
    assert "detection search-period" not in tools
    assert ("modeling fit-transit" in tools) == (stage in ("select", "fit"))
    assert ("vetting run-gates" in tools) == (stage != "review")
