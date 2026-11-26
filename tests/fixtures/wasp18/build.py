"""Build the WASP-18 b fixtures from public catalogs (network; run by hand).

    uv run python -m tests.fixtures.wasp18.build

Writes into tests/fixtures/wasp18/:
- reference.json: TIC id and orbital period of WASP-18 b, from the NASA Exoplanet
  Archive (TAP, table pscomppars), with the query, URL and retrieval time.
- tic_target.json, tic_neighbors.json: the TIC rows that fetch-star reads.
- s<sector>_trimmed.fits: SPOC 2-minute light curves of the first two sectors chosen
  by the mission rule, trimmed to a few days and to the columns the hub reads.
- catalogs.json: the raw answers crossmatch reads (pscomppars and toi rows from the
  NASA Exoplanet Archive TAP, and the ctois and planet_parameters of the ExoFOP target).
- PROVENANCE.md: where every file comes from and how it was trimmed.

Nothing astronomical is typed by hand: the TIC id and the period come from the query.
"""

import hashlib
import json
import tempfile
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

from contexts.acquisition.domain.sectors import select_sectors
from contexts.acquisition.infrastructure.mast import MastLightcurveArchive, MastTicCatalog
from contexts.catalog.infrastructure.archive import (
    exofop_url,
    http_json,
    pscomppars_query,
    tap_url,
    toi_query,
)
from shared.mission import load_mission
from shared.toolkit.caches import isolated_caches

HERE = Path(__file__).resolve().parent
PLANET = "WASP-18 b"
TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
TAP_QUERY = (
    "select pl_name,tic_id,pl_orbper,pl_orbpererr1,pl_orbpererr2,pl_orbper_reflink "
    f"from pscomppars where pl_name='{PLANET}'"
)
KEEP_DAYS = 5.0  # length of the window kept from each sector (>= 6 transits in total)
N_SECTORS = 2
COLUMNS = ("TIME", "PDCSAP_FLUX", "PDCSAP_FLUX_ERR", "QUALITY", "MOM_CENTR1", "MOM_CENTR2")
TIC_COLUMNS = (
    "ID", "version", "ra", "dec", "Tmag", "contratio", "dstArcSec",
    "Teff", "e_Teff", "eneg_Teff", "epos_Teff",
    "logg", "e_logg", "eneg_logg", "epos_logg",
    "rad", "e_rad", "eneg_Rad", "epos_Rad",
    "mass", "e_mass", "eneg_Mass", "epos_Mass",
)  # fmt: skip


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name: str, payload: Any) -> None:
    (HERE / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def query_reference() -> dict[str, Any]:
    url = TAP_URL + "?" + urllib.parse.urlencode({"query": TAP_QUERY, "format": "json"})
    with urllib.request.urlopen(url, timeout=60) as response:
        rows = json.load(response)
    if len(rows) != 1:
        raise SystemExit(f"expected one row for {PLANET}, got {len(rows)}")
    row = rows[0]
    tic = str(row["tic_id"])
    if not tic.startswith("TIC "):
        raise SystemExit(f"unexpected tic_id format: {tic!r}")
    return {
        "planet": row["pl_name"],
        "tic_id": int(tic.removeprefix("TIC ")),
        "period_days": row["pl_orbper"],
        "period_err_upper_days": row["pl_orbpererr1"],
        "period_err_lower_days": row["pl_orbpererr2"],
        "period_reference_html": row["pl_orbper_reflink"],
        "source": (
            "NASA Exoplanet Archive, Planetary Systems Composite Parameters (pscomppars), TAP"
        ),
        "query": TAP_QUERY,
        "url": url,
        "retrieved_at": now(),
    }


def query_catalogs(tic_id: int) -> dict[str, Any]:
    """The answers crossmatch reads, as the services return them."""
    tap = {"pscomppars": tap_url(pscomppars_query(tic_id)), "toi": tap_url(toi_query(tic_id))}
    target = http_json(exofop_url(tic_id))
    return {
        "retrieved_at": now(),
        **{name: {"url": url, "rows": http_json(url)} for name, url in tap.items()},
        "exofop": {
            "url": exofop_url(tic_id),
            "target": {k: target.get(k, []) for k in ("ctois", "planet_parameters")},
        },
    }


def best_window(valid_times: np.ndarray, days: float) -> float:
    """Start of the window of `days` with the most valid cadences (ties: the earliest)."""
    times = np.sort(valid_times)
    counts = np.searchsorted(times, times + days, side="left") - np.arange(times.size)
    return float(times[int(np.argmax(counts))])


def trim(source: Path, dest: Path, sector: int) -> dict[str, Any]:
    with fits.open(source, memmap=False) as hdul:
        primary = hdul[0].header.copy()
        table = hdul[1].data
        time = np.array(table["TIME"])
        valid = (
            np.isfinite(time)
            & np.isfinite(np.array(table["PDCSAP_FLUX"]))
            & (np.array(table["QUALITY"]) == 0)
        )
        start = best_window(time[valid], KEEP_DAYS)
        rows = np.flatnonzero(np.isfinite(time) & (time >= start) & (time < start + KEEP_DAYS))
        cols = [
            fits.Column(name=name, format=hdul[1].columns[name].format, array=table[name][rows])
            for name in COLUMNS
        ]
    for key in ("CHECKSUM", "DATASUM"):
        primary.remove(key, ignore_missing=True)
    primary.add_history(f"Trimmed by astronomy-hub tests/fixtures/wasp18/build.py on {now()}")
    primary.add_history(f"Kept rows {rows[0]}-{rows[-1]} and columns {', '.join(COLUMNS)}")
    hdu = fits.BinTableHDU.from_columns(cols, name="LIGHTCURVE")
    fits.HDUList([fits.PrimaryHDU(header=primary), hdu]).writeto(dest, overwrite=True)
    return {
        "sector": sector,
        "original_file": source.name,
        "original_uri": f"mast:TESS/product/{source.name}",
        "original_sha256": sha256(source),
        "rows_kept": [int(rows[0]), int(rows[-1])],
        "time_range_btjd": [float(time[rows[0]]), float(time[rows[-1]])],
        "fixture": dest.name,
        "fixture_sha256": sha256(dest),
    }


def main() -> None:
    reference = query_reference()
    tic_id = reference["tic_id"]
    write_json("reference.json", reference)
    catalogs = query_catalogs(tic_id)
    write_json("catalogs.json", catalogs)
    mission = load_mission("exoplanets").acquisition

    with tempfile.TemporaryDirectory() as tmp, isolated_caches(Path(tmp) / ".cache"):
        catalog = MastTicCatalog()
        target = catalog.target(tic_id)
        neighbors = catalog.neighbors(target["ra"], target["dec"], mission.neighbor_radius_arcsec)
        retrieved = now()
        write_json(
            "tic_target.json",
            {"retrieved_at": retrieved, "row": {k: target.get(k) for k in TIC_COLUMNS}},
        )
        write_json(
            "tic_neighbors.json",
            {
                "retrieved_at": retrieved,
                "radius_arcsec": mission.neighbor_radius_arcsec,
                "rows": [{k: row.get(k) for k in TIC_COLUMNS} for row in neighbors],
            },
        )

        archive = MastLightcurveArchive()
        available = archive.available_sectors(tic_id, mission.author, mission.exptime_s)
        chosen = select_sectors(available, mission.sector_selection.max_sectors)[:N_SECTORS]
        files = archive.download(tic_id, chosen, mission.author, mission.exptime_s, Path(tmp))
        trimmed = [trim(files[s], HERE / f"s{s:04d}_trimmed.fits", s) for s in sorted(files)]
    write_json(
        "light_curves.json",
        {"retrieved_at": now(), "available_sectors": available, "files": trimmed},
    )
    lines = [
        "# WASP-18 b fixtures",
        "",
        "Generated by `uv run python -m tests.fixtures.wasp18.build` (network).",
        "Do not edit by hand.",
        "",
        f"- `reference.json`: {reference['source']}, retrieved {reference['retrieved_at']}.",
        f"  Query: `{reference['query']}`.",
        f"- `tic_target.json`, `tic_neighbors.json`: MAST TIC (astroquery `Catalogs`), "
        f"retrieved {retrieved}; cone of {mission.neighbor_radius_arcsec} arcsec.",
        f"- `catalogs.json`: NASA Exoplanet Archive TAP (`pscomppars`, `toi`) and ExoFOP "
        f"(`ctois`, `planet_parameters` of the target), retrieved {catalogs['retrieved_at']}; "
        "the URLs are in the file.",
        f"- SPOC 2-minute light curves from MAST, first {N_SECTORS} sectors chosen by the "
        f"mission rule from {available}. Each keeps the {KEEP_DAYS:g}-day window with the "
        f"most valid cadences (finite PDCSAP_FLUX, QUALITY == 0) and only "
        f"the columns {', '.join(COLUMNS)}; the primary header is the original one plus HISTORY:",
    ]
    for t in trimmed:
        lines.append(
            f"  - `{t['fixture']}`: sector {t['sector']}, from `{t['original_uri']}` "
            f"({t['original_sha256']}), rows {t['rows_kept'][0]}-{t['rows_kept'][1]}."
        )
    (HERE / "PROVENANCE.md").write_text("\n".join(lines) + "\n")
    total = sum(p.stat().st_size for p in HERE.iterdir() if p.is_file())
    print(json.dumps({"tic_id": tic_id, "sectors": chosen, "fixture_bytes": total}))


if __name__ == "__main__":
    main()
