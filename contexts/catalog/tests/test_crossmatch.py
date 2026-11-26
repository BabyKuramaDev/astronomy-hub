from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from contexts.catalog.application.crossmatch import Crossmatch
from contexts.catalog.domain.crossmatch import (
    CatalogEntry,
    catalog_status,
    match_entries,
    period_ratio,
)
from contexts.catalog.infrastructure.archive import (
    ArchiveCatalogs,
    parse_confirmed,
    parse_ctois,
    parse_tois,
)
from shared.contracts import CatalogFile, SignalData
from shared.kernel.contexts import Context
from shared.mission import load_mission
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import DataNotAvailableError
from shared.toolkit.meta import ToolMeta
from shared.toolkit.retry import RetryPolicy

TIC = 77
CONFIG = load_mission("exoplanets").catalog


def entry(catalog: str, period: float | None, disposition: str | None = None) -> CatalogEntry:
    return CatalogEntry(catalog, f"{catalog}-x", period, disposition, "https://example.org/x")


@pytest.mark.parametrize(
    ("catalog_period", "expected"),
    [(2.0, "1/1"), (2.015, "1/1"), (4.0, "2/1"), (1.0, "1/2"), (0.4, "1/5"), (2.5, None)],
)
def test_period_ratio(catalog_period: float, expected: str | None) -> None:
    assert period_ratio(catalog_period, 2.0, 0.01, 10) == expected


@pytest.mark.parametrize(
    ("entries", "status"),
    [
        ([entry("pscomppars", 2.0, "CONFIRMED")], "known_planet"),
        ([entry("toi", 2.0, "KP")], "known_planet"),
        ([entry("toi", 4.0, "PC")], "toi"),
        ([entry("toi", 2.0, "FP")], "known_false_positive"),
        ([entry("ctoi", 1.0, "PC")], "ctoi"),
        ([entry("toi", 3.1, "PC")], "unknown"),  # another period: not this signal
        ([entry("toi", 3.1, "PC"), entry("ctoi", 2.0, "PC")], "ctoi"),
        ([entry("toi", 2.0, "FP"), entry("pscomppars", 2.0, "CONFIRMED")], "known_planet"),
        ([], "unknown"),
    ],
)
def test_status_only_counts_period_matches(entries: list[CatalogEntry], status: str) -> None:
    assert catalog_status(match_entries(entries, 2.0, 0.01, 10)) == status


def test_without_signal_every_entry_counts() -> None:
    matched = match_entries([entry("toi", 3.1, "PC")], None, 0.01, 10)
    assert matched[0].period_match is None
    assert catalog_status(matched) == "toi"


def test_parsers() -> None:
    confirmed = parse_confirmed([{"pl_name": "Example-1 b", "pl_orbper": 3.5}])
    assert confirmed[0].disposition == "CONFIRMED"
    assert confirmed[0].url.endswith("/overview/Example-1%20b")
    tois = parse_tois([{"toi": 101.01, "tfopwg_disp": None, "pl_orbper": None}], TIC)
    assert (tois[0].id, tois[0].disposition, tois[0].period_days) == ("TOI-101.01", None, None)
    target = {
        "ctois": [{"ctoi": "TIC 77.01", "cdisp": "PC", "tdisp": ""}],
        "planet_parameters": [{"prov": "ctoi"}, {"name": "TIC 77.01", "per": "2.5"}],
    }
    ctois = parse_ctois(target, TIC)
    assert (ctois[0].period_days, ctois[0].disposition) == (2.5, "PC")


class FakeCatalogs:
    def confirmed_planets(self, tic_id: int) -> list[CatalogEntry]:
        return [entry("pscomppars", 2.0, "CONFIRMED")]

    def tois(self, tic_id: int) -> list[CatalogEntry]:
        return [entry("toi", 7.3, "PC")]

    def ctois(self, tic_id: int) -> list[CatalogEntry]:
        return []

    def describe(self) -> str:
        return "fake"


def meta(context: Context, tool: str) -> ToolMeta:
    return ToolMeta(context, tool, TIC, "exoplanets", "0.1.0", lambda: datetime.now(UTC))


def test_crossmatch_writes_catalog_with_notes(tmp_path: Path) -> None:
    dossier = Dossier(tmp_path)
    signal = SignalData(
        detected=True,
        period_days=4.0,
        epoch_btjd=1000.0,
        duration_hours=2.0,
        depth_ppm=1000.0,
        snr=20.0,
        n_transits=5,
        sectors=[1],
        method="bls",
        other_peaks=[],
    )
    dossier.write_envelope(
        "signal.json", meta(Context.DETECTION, "select-peak").envelope(signal, {})
    )
    summary = Crossmatch(
        FakeCatalogs(), Dossier(tmp_path), meta(Context.CATALOG, "crossmatch"), CONFIG
    ).execute()
    catalog = Dossier(tmp_path).read_envelope("catalog.json", CatalogFile)
    assert catalog.data.status == "known_planet" == summary["status"]
    assert [m.period_match for m in catalog.data.matches] == [True, False]
    assert summary["matches"][0]["ratio"] == "1/2"
    assert any("does not match" in n for n in catalog.data.notes)
    assert "signal.json" in catalog.inputs


def test_transient_errors_are_retried_then_data_not_available() -> None:
    calls = []

    def down(url: str) -> object:
        calls.append(url)
        raise requests.ConnectionError("archive down")

    catalogs = ArchiveCatalogs(RetryPolicy(3, 1.0, lambda _: None), fetch=down)
    with pytest.raises(DataNotAvailableError, match="pscomppars query failed"):
        catalogs.confirmed_planets(TIC)
    assert len(calls) == 3


def test_add_literature(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from contexts.catalog.cli import main

    root = tmp_path / "exoplanets" / str(TIC)
    argv = ["add-literature", "--tic", str(TIC), "--workspace", str(tmp_path),
            "--title", "Discovery paper", "--url", "https://arxiv.org/abs/0000.00000",
            "--note", "Reports the period."]  # fmt: skip
    assert main(argv) == 2  # no catalog.json yet
    assert "run crossmatch first" in capsys.readouterr().err
    Crossmatch(FakeCatalogs(), Dossier(root), meta(Context.CATALOG, "crossmatch"), CONFIG).execute()
    before = Dossier(root).read_envelope("catalog.json", CatalogFile)
    assert main(argv) == 0
    assert main(argv) == 0  # same URL: not added twice
    after = Dossier(root).read_envelope("catalog.json", CatalogFile)
    assert [r.title for r in after.data.literature] == ["Discovery paper"]
    assert after.inputs == before.inputs
    assert after.data.status == before.data.status
    bad = [*argv[:-4], "--url", "not a url"]
    assert main(bad) == 2
