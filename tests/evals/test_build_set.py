import json
from pathlib import Path

import pytest

from contexts.acquisition.domain.sectors import select_sectors as acquisition_rule
from evals.build_set import build
from evals.selection import QUOTAS, candidates, searchable, select_sectors

TOI_ROW = {"st_tmag": 10.0}


def toi(tid: int, disp: str, period: float, depth: float, toi_id: str | None = None) -> dict:
    return {
        **TOI_ROW,
        "tid": tid,
        "toi": toi_id or f"{tid}.01",
        "tfopwg_disp": disp,
        "pl_orbper": period,
        "pl_trandep": depth,
    }


@pytest.mark.parametrize(
    "available", [[], [5], [1, 2, 3, 10, 11], [1, 2, 5, 6, 7, 8, 9, 10], [3, 4, 20, 21]]
)
def test_sector_rule_matches_acquisition(available: list[int]) -> None:
    assert select_sectors(available, 4) == acquisition_rule(available, 4)


def test_searchable() -> None:
    assert searchable(3.0, 54.8, 0.5, 15.0, 3)
    assert not searchable(20.0, 54.8, 0.5, 15.0, 3)  # outside the search range
    assert not searchable(14.0, 27.4, 0.5, 15.0, 3)  # fewer than 3 transits in one sector


def test_catalog_filters() -> None:
    tois = [
        toi(1, "CP", 2.0, 5000.0),
        toi(2, "CP", 3.0, 400.0),
        toi(3, "FP", 4.0, 800.0),
        toi(4, "CP", 2.0, 5000.0),
        toi(4, "PC", 9.0, 300.0),  # two TOIs: out
        toi(5, "CP", 40.0, 5000.0),  # period out of range
        toi(6, "KP", 2.0, 9000.0),  # known before TESS: out
        toi(7, "FP", 2.0, 900.0),  # has a CTOI: out
        toi(8, "CP", 2.0, 5000.0),  # host has a famous name: out
    ]
    planets = [
        {"pl_name": "TOI-1 b", "tic_id": "TIC 1"},
        {"pl_name": "TOI-2 b", "tic_id": "TIC 2"},
        {"pl_name": "WASP-999 b", "tic_id": "TIC 8"},
    ]
    pools = candidates(tois, planets, {7}, set(), 0.5, 15.0)
    assert [s.tic_id for s in pools["planet_deep"]] == [1]
    assert [s.tic_id for s in pools["planet_small"]] == [2]
    assert [s.tic_id for s in pools["false_positive"]] == [3]


def synthetic_snapshot(root: Path) -> None:
    snap = root / "snapshot"
    (snap / "mast").mkdir(parents=True)
    tois, planets = [], []
    for k in range(30):
        tois.append(toi(1000 + k, "CP", 2.0 + k / 10, 5000.0 if k % 2 else 500.0))
        planets.append({"pl_name": f"TOI-{1000 + k} b", "tic_id": f"TIC {1000 + k}"})
        tois.append(toi(3000 + k, "FP", 3.0, 2000.0))
    quiet = list(range(5000, 5030))

    def save(name: str, data: object) -> None:
        (snap / f"{name}.json").write_text(json.dumps({"retrieved_at": "x", "data": data}))

    save("toi", tois)
    save("pscomppars", planets)
    save("ctoi", [])
    save("sector_92", quiet)
    for tic in [r["tid"] for r in tois] + quiet:
        # every seventh star lacks light curves and must be skipped
        good = tic % 7 != 0
        save(
            f"mast/{tic}",
            {"available": [90, 91], "chosen": [90, 91] if good else [], "lc_products": good},
        )


def test_build_from_snapshot_is_reproducible(tmp_path: Path) -> None:
    synthetic_snapshot(tmp_path)
    first = build(tmp_path, offline=True)
    text = (tmp_path / "set.json").read_text()
    assert build(tmp_path, offline=True)["set_hash"] == first["set_hash"]
    assert (tmp_path / "set.json").read_text() == text
    stars = json.loads(text)["stars"]
    for group, (total, dev) in QUOTAS.items():
        rows = [s for s in stars if s["group"] == group]
        assert len(rows) == total
        assert sum(s["split"] == "dev" for s in rows) == dev
    assert all(s["tic_id"] % 7 for s in stars), "stars without light curves are skipped"
