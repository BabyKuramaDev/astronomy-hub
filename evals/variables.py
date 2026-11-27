"""Is a quiet star a catalogued eclipsing binary? (offline once the catalogue is saved)

    uv run python -m evals.variables [--set v0.1-calib] [--splits calib]

Looks up every no_signal star by TIC in the TESS eclipsing-binary catalogue (Prša et al.
2022, ApJS 258, 16; 4584 EBs from sectors 1 to 26), as published by MAST:
https://archive.stsci.edu/hlsps/tess-ebs/ — saved in <evals_dir>/catalogs/. A star found
there is listed, to leave it out of the negatives when calibrating. The catalogue only
covers stars observed in sectors 1 to 26. Gaia DR3 variability (ESA TAP), SIMBAD and VSX
(VizieR, AAVSO) could not be queried on 2026-11-27: their query endpoints answered with
web pages, 404 or 403 instead of data.
"""

import argparse
import csv
import json
from typing import Any

from evals.paths import evals_dir

CATALOG = "hlsp_tess-ebs_tess_lcf-ffi_s0001-s0026_tess_v1.0_cat.csv"
URL = "https://archive.stsci.edu/hlsps/tess-ebs/" + CATALOG


def tess_ebs() -> dict[int, dict[str, Any]]:
    path = evals_dir() / "catalogs" / CATALOG
    if not path.exists():
        raise SystemExit(f"download {URL} into {path.parent} first")
    with path.open(newline="") as handle:
        return {
            int(r["tess_id"]): {
                "period_days": float(r["period"]) if r["period"] else None,
                "morph_coeff": r["morph_coeff"],
                "sectors": r["sectors"],
            }
            for r in csv.DictReader(handle)
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.variables")
    parser.add_argument("--set", default="v0.1-calib", dest="set_id")
    parser.add_argument("--splits", default="calib,dev")
    args = parser.parse_args(argv)
    meta = json.loads((evals_dir() / "sets" / args.set_id / "set.json").read_text())
    splits = set(args.splits.split(","))
    ebs = tess_ebs()
    quiet = [
        s["tic_id"] for s in meta["stars"] if s["group"] == "no_signal" and s["split"] in splits
    ]
    found = {tic: ebs[tic] for tic in quiet if tic in ebs}
    print(
        json.dumps({"catalog": URL, "checked": len(quiet), "eclipsing_binaries": found}, indent=1)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
