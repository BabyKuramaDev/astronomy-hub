"""Build the eval set from public catalogs, with a fixed seed (network; run by hand).

    uv run python -m evals.build_set [--set v0.1]          # query the catalogs and MAST
    uv run python -m evals.build_set --from-snapshot      # rebuild from the saved answers
    uv run python -m evals.build_set --set v0.1-calib     # calibration set (baseline only)

Writes <evals_dir>/sets/<set_id>/: set.json (stars, group, split, catalog period and
depth) and snapshot/ (every raw answer: the TOI and pscomppars tables, the CTOI list,
the 120 s targets of one sector and each MAST check). Nothing goes into this
repository: the sandbox mounts it. Rebuilding from the snapshot gives the same
set.json byte for byte; results record its sha256.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.paths import REPO, evals_dir
from evals.selection import QUOTAS, Star, candidates, searchable, select_sectors, shuffled, split
from shared.mission import load_mission
from shared.toolkit.caches import isolated_caches
from shared.toolkit.retry import RetryPolicy

# v0.1: development and holdout. v0.1-calib: calibration set for the rules (baseline only),
# same filters and catalog snapshot, none of v0.1's stars; a group may come up short.
PROFILES: dict[str, dict[str, Any]] = {
    "v0.1": {"seed": 20261127, "quotas": QUOTAS, "labels": ("dev", "holdout")},
    "v0.1-calib": {
        "seed": 20261128,
        "quotas": {
            "planet_deep": (30, 30),
            "planet_small": (30, 30),
            "false_positive": (60, 60),
            "no_signal": (30, 30),
        },
        "labels": ("calib", "calib"),
        "base": "v0.1",  # reuse its catalog snapshot and exclude its stars
        "allow_short": True,
    },
}
TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
TOI_QUERY = "select tid,toi,tfopwg_disp,pl_orbper,pl_trandep,st_tmag from toi"
PLANET_QUERY = "select pl_name,tic_id,hostname from pscomppars where tic_id is not null"
CTOI_URL = "https://exofop.ipac.caltech.edu/tess/download_ctoi.php?sort=ctoi&output=pipe"
NO_SIGNAL_SECTOR = 92  # a recent sector; its SPOC 120 s targets feed the no-signal group
SECTOR_DAYS = 27.4  # nominal length of a TESS sector, only for the expected-transits filter
SINGLE_SECTOR = re.compile(r"^tess\d{13}-s(?P<sector>\d{4})-\d{16}-\d{4}-s$")
RETRY = RetryPolicy(4, 2.0)
WASP18 = json.loads((REPO / "tests" / "fixtures" / "wasp18" / "reference.json").read_text())


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class Snapshot:
    """Every raw answer goes through here: saved when online, read back when offline."""

    def __init__(self, root: Path, offline: bool, base: Path | None = None) -> None:
        self.root, self.offline, self.base = root, offline, base
        root.mkdir(parents=True, exist_ok=True)

    def get(self, name: str, fetch: Callable[[], Any], meta: dict[str, str]) -> Any:
        path = self.root / f"{name}.json"
        if not path.exists() and self.base is not None and (self.base / f"{name}.json").exists():
            path.parent.mkdir(parents=True, exist_ok=True)  # same answer, same date
            path.write_text((self.base / f"{name}.json").read_text())
        if path.exists():
            return json.loads(path.read_text())["data"]
        if self.offline:
            raise SystemExit(f"snapshot has no {name}: rebuild online")
        data = RETRY.call(fetch)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"retrieved_at": now(), **meta, "data": data}, indent=1) + "\n")
        return data


def http(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "astronomy-hub-evals/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def tap(query: str) -> Callable[[], Any]:
    url = TAP + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    return lambda: json.loads(http(url))


def ctoi_tics() -> list[int]:
    lines = http(CTOI_URL).decode().splitlines()
    column = lines[0].split("|").index("TIC ID")
    return sorted({int(line.split("|")[column]) for line in lines[1:] if line.strip()})


def mast_check(tic: int) -> dict[str, Any]:
    """Single-sector SPOC 120 s observations, the sectors the mission rule picks, and
    whether each has a light curve product (checked in the product list, not downloaded)."""
    from astroquery.mast import Observations

    obs = Observations.query_criteria(
        target_name=str(tic),
        obs_collection="TESS",
        dataproduct_type="timeseries",
        provenance_name="SPOC",
        t_exptime=[119, 121],
    )
    rows = [
        r
        for r in obs
        if (m := SINGLE_SECTOR.match(str(r["obs_id"])))
        and int(m["sector"]) == int(r["sequence_number"])
    ]
    sectors = sorted({int(r["sequence_number"]) for r in rows})
    max_sectors = load_mission("exoplanets").acquisition.sector_selection.max_sectors
    chosen = select_sectors(sectors, max_sectors)
    picked = [r for r in rows if int(r["sequence_number"]) in chosen]
    lc_ok = False
    if picked:
        products = Observations.get_product_list(obs[[r.index for r in picked]])
        names = {
            str(p["productFilename"]) for p in products if p["productSubGroupDescription"] == "LC"
        }
        lc_ok = sum(1 for n in names if n.endswith("_lc.fits")) >= len(chosen)
    return {"available": sectors, "chosen": chosen, "lc_products": lc_ok}


def sector_targets(sector: int) -> list[int]:
    from astroquery.mast import Observations

    obs = Observations.query_criteria(
        obs_collection="TESS",
        dataproduct_type="timeseries",
        provenance_name="SPOC",
        t_exptime=[119, 121],
        sequence_number=sector,
    )
    return sorted({int(r["target_name"]) for r in obs if str(r["target_name"]).isdigit()})


def build(out: Path, offline: bool, set_id: str = "v0.1") -> dict[str, Any]:
    profile = PROFILES[set_id]
    quotas, seed = profile["quotas"], profile["seed"]
    mission = load_mission("exoplanets").detection
    base = out.parent / profile["base"] if "base" in profile else None
    snap = Snapshot(out / "snapshot", offline, base / "snapshot" if base else None)
    tois = snap.get("toi", tap(TOI_QUERY), {"query": TOI_QUERY, "source": TAP})
    planets = snap.get("pscomppars", tap(PLANET_QUERY), {"query": PLANET_QUERY, "source": TAP})
    ctois = set(snap.get("ctoi", ctoi_tics, {"source": CTOI_URL}))
    excluded = {int(WASP18["tic_id"])}
    if base is not None:
        excluded |= {int(s["tic_id"]) for s in json.loads((base / "set.json").read_text())["stars"]}
    pools = candidates(
        tois, planets, ctois, excluded, mission.period_min_days, mission.period_max_days
    )
    toi_tics = {int(r["tid"]) for r in tois}
    planet_tics = {
        int(str(r["tic_id"]).removeprefix("TIC "))
        for r in planets
        if str(r.get("tic_id") or "").startswith("TIC ")
    }
    quiet = snap.get(
        f"sector_{NO_SIGNAL_SECTOR}",
        lambda: sector_targets(NO_SIGNAL_SECTOR),
        {"source": "MAST Observations, SPOC 120 s"},
    )
    pools["no_signal"] = [
        Star(t, "no_signal", None, None, None, None)
        for t in quiet
        if t not in toi_tics | planet_tics | ctois | excluded
    ]

    chosen: dict[str, list[Star]] = {}
    rejected: dict[str, list[dict[str, Any]]] = {}
    for group, (quota, _dev) in quotas.items():
        chosen[group], rejected[group] = [], []
        for star in shuffled(pools[group], seed, group):
            if len(chosen[group]) == quota:
                break
            check = snap.get(
                f"mast/{star.tic_id}",
                lambda t=star.tic_id: mast_check(t),
                {"source": "MAST Observations"},
            )
            baseline = SECTOR_DAYS * len(check["chosen"])
            ok = bool(check["chosen"]) and check["lc_products"]
            if ok and star.period_days is not None:
                ok = searchable(
                    star.period_days,
                    baseline,
                    mission.period_min_days,
                    mission.period_max_days,
                    mission.min_transits,
                )
            if ok:
                chosen[group].append(star)
            else:
                rejected[group].append({"tic_id": star.tic_id, **check})
        if len(chosen[group]) < quota and not profile.get("allow_short"):
            raise SystemExit(f"only {len(chosen[group])} stars qualify for {group}")
    stars = split(chosen, quotas, profile["labels"])
    body = {
        "set_id": set_id,
        "seed": seed,
        "no_signal_sector": NO_SIGNAL_SECTOR,
        "filters": {
            "period_min_days": mission.period_min_days,
            "period_max_days": mission.period_max_days,
            "min_transits": mission.min_transits,
            "excluded": sorted(excluded),
            "quotas": quotas,
        },
        "stars": stars,
        **({"base_set": profile["base"]} if "base" in profile else {}),
    }
    digest = "sha256:" + hashlib.sha256(canonical(body)).hexdigest()
    (out / "set.json").write_text(
        json.dumps({**body, "set_hash": digest}, indent=1, sort_keys=True) + "\n"
    )
    (out / "rejected.json").write_text(json.dumps(rejected, indent=1, sort_keys=True) + "\n")
    return {
        "set_id": set_id,
        "per_group": {g: len(c) for g, c in chosen.items()},
        "set_hash": digest,
        "stars": len(stars),
        "rejected": {g: len(r) for g, r in rejected.items()},
        "dir": str(out),
    }


def commit_snapshot(root: Path, message: str) -> None:
    """The evals folder keeps its own local git history (no remote, never pushed)."""
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False)
    if staged.returncode != 0:
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


def build_commit() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.build_set")
    parser.add_argument("--from-snapshot", action="store_true", help="no network: reuse answers")
    parser.add_argument("--set", default="v0.1", choices=sorted(PROFILES), dest="set_id")
    args = parser.parse_args(argv)
    root = evals_dir()
    out = root / "sets" / args.set_id
    with tempfile.TemporaryDirectory() as tmp, isolated_caches(Path(tmp) / ".cache"):
        result = build(out, offline=args.from_snapshot, set_id=args.set_id)
    result["build_commit"] = build_commit()
    if not args.from_snapshot:
        commit_snapshot(
            root,
            f"Build set {args.set_id} ({result['set_hash'][:19]}) with build_set at "
            f"{result['build_commit']}",
        )
    print(json.dumps(result, indent=2), file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
