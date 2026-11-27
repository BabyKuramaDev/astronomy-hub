"""Pure rules of the eval set: which catalog rows qualify and how the set is split.

No I/O: build_set.py feeds it the catalog snapshots and the MAST checks.
"""

import random
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

PLANET = frozenset({"CP"})  # confirmed by TESS follow-up; KP are mostly pre-TESS famous names
FALSE_POSITIVE = frozenset({"FP", "FA"})
DEEP_PPM = 1000.0
# Per group: (stars in the set, of which in the development split).
QUOTAS = {
    "planet_deep": (10, 6),
    "planet_small": (10, 6),
    "false_positive": (20, 12),
    "no_signal": (10, 6),
}


def consecutive_runs(sectors: Iterable[int]) -> list[list[int]]:
    """Same rule as acquisition (longest_consecutive_run); a test keeps them equal."""
    runs: list[list[int]] = []
    for sector in sorted(set(sectors)):
        if runs and sector == runs[-1][-1] + 1:
            runs[-1].append(sector)
        else:
            runs.append([sector])
    return runs


def select_sectors(available: Iterable[int], max_sectors: int) -> list[int]:
    runs = consecutive_runs(available)
    if not runs:
        return []
    return max(runs, key=lambda run: (len(run), run[-1]))[-max_sectors:]


def searchable(
    period: float, baseline_days: float, p_min: float, p_max: float, min_transits: int
) -> bool:
    """The search can reach the period and the chosen sectors hold min_transits of it."""
    if not p_min <= period <= p_max:
        return False
    return period <= baseline_days / max(min_transits - 1, 1)


@dataclass(frozen=True)
class Star:
    tic_id: int
    group: str  # planet_deep | planet_small | false_positive | no_signal
    toi: str | None
    disposition: str | None
    period_days: float | None
    depth_ppm: float | None


def candidates(
    tois: Sequence[dict],
    planets: Sequence[dict],
    ctoi_tics: set[int],
    excluded: set[int],
    p_min: float,
    p_max: float,
) -> dict[str, list[Star]]:
    """Catalog-only filters: one TOI per star, no other planet, no CTOI, period in range."""
    per_star = Counter(int(r["tid"]) for r in tois)
    hosts: dict[int, list[str]] = {}
    for row in planets:
        tic = str(row.get("tic_id") or "")
        if tic.startswith("TIC "):
            hosts.setdefault(int(tic.removeprefix("TIC ")), []).append(str(row["pl_name"]))
    pools: dict[str, list[Star]] = {g: [] for g in QUOTAS if g != "no_signal"}
    for row in tois:
        tic = int(row["tid"])
        disposition, period = row.get("tfopwg_disp"), row.get("pl_orbper")
        if per_star[tic] != 1 or tic in ctoi_tics or tic in excluded or period is None:
            continue
        if not p_min <= float(period) <= p_max:
            continue
        depth = float(row["pl_trandep"]) if row.get("pl_trandep") is not None else None
        star_planets = hosts.get(tic, [])
        if disposition in PLANET:
            if len(star_planets) != 1 or not star_planets[0].startswith("TOI-") or depth is None:
                continue
            group = "planet_deep" if depth > DEEP_PPM else "planet_small"
        elif disposition in FALSE_POSITIVE:
            if star_planets:
                continue
            group = "false_positive"
        else:
            continue
        pools[group].append(Star(tic, group, str(row["toi"]), disposition, float(period), depth))
    return {g: sorted(stars, key=lambda s: s.tic_id) for g, stars in pools.items()}


def shuffled(stars: Sequence[Star], seed: int, group: str) -> list[Star]:
    order = sorted(stars, key=lambda s: s.tic_id)
    random.Random(f"{seed}:{group}").shuffle(order)
    return order


def split(
    chosen: dict[str, list[Star]],
    quotas: dict[str, tuple[int, int]] = QUOTAS,
    labels: tuple[str, str] = ("dev", "holdout"),
) -> list[dict]:
    """The first quota[1] stars of each group (shuffled order) get labels[0], the rest
    labels[1]: development and holdout for v0.1; all calib for the calibration set."""
    rows = []
    for group, stars in chosen.items():
        _total, first = quotas[group]
        for k, star in enumerate(stars):
            rows.append({**asdict(star), "split": labels[0] if k < first else labels[1]})
    return sorted(rows, key=lambda r: (r["group"], r["tic_id"]))


PILOT = {"planet_deep": 1, "planet_small": 1, "false_positive": 2, "no_signal": 1}


def pilot(stars: Sequence[dict]) -> list[dict]:
    """The pilot: the first development stars of each group, by TIC (deterministic)."""
    out = []
    for group, k in PILOT.items():
        dev = sorted(
            (s for s in stars if s["group"] == group and s["split"] == "dev"),
            key=lambda s: s["tic_id"],
        )
        out += dev[:k]
    return out
