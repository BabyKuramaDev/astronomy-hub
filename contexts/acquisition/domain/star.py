"""Build star.json data from TIC catalog rows."""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from shared.contracts import Measurement, Neighbor, StarData

Row = Mapping[str, Any]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def measurement(row: Row, value: str, err: str, err_neg: str, err_pos: str) -> Measurement | None:
    """Value with its error; asymmetric errors are preferred over the symmetric one.

    Returns None unless both the value and its errors are present.
    """
    center = _number(row.get(value))
    symmetric = _number(row.get(err))
    lower = _number(row.get(err_neg))
    upper = _number(row.get(err_pos))
    lower = lower if lower is not None else symmetric
    upper = upper if upper is not None else symmetric
    if center is None or lower is None or upper is None:
        return None
    return Measurement(value=center, err_lower=abs(lower), err_upper=abs(upper))


def build_star(
    target: Row, neighbors: Sequence[Row], radius_arcsec: float, source: str
) -> StarData:
    ra = _number(target.get("ra"))
    dec = _number(target.get("dec"))
    if ra is None or dec is None:
        raise ValueError("TIC row has no coordinates")
    target_id = int(target["ID"])
    near = []
    for row in neighbors:
        tic_id = int(row["ID"])
        sep = _number(row.get("dstArcSec"))
        if tic_id == target_id or sep is None or sep > radius_arcsec:
            continue
        near.append(Neighbor(tic_id=tic_id, separation_arcsec=sep, tmag=_number(row.get("Tmag"))))
    near.sort(key=lambda n: (n.separation_arcsec, n.tic_id))
    contamination = _number(target.get("contratio"))
    return StarData(
        ra_deg=ra % 360.0,
        dec_deg=dec,
        tmag=_number(target.get("Tmag")),
        teff_k=measurement(target, "Teff", "e_Teff", "eneg_Teff", "epos_Teff"),
        logg=measurement(target, "logg", "e_logg", "eneg_logg", "epos_logg"),
        radius_rsun=measurement(target, "rad", "e_rad", "eneg_Rad", "epos_Rad"),
        mass_msun=measurement(target, "mass", "e_mass", "eneg_Mass", "epos_Mass"),
        contamination_ratio=contamination if contamination is None or contamination >= 0 else None,
        source=source,
        neighbor_radius_arcsec=radius_arcsec,
        neighbors=near,
    )
