"""Crossmatch rules: period matches (aliases included) and the catalog status.

A catalog entry matches the signal when its period is within `tolerance` of the
signal's period or of an integer multiple or submultiple of it (up to
`max_integer`). The status only looks at entries that match in period; entries at
another period are recorded as notes and do not make the signal known.
"""

from collections.abc import Sequence
from dataclasses import dataclass

# Dispositions, as written by the catalogs.
CONFIRMED = "CONFIRMED"  # NASA Exoplanet Archive pscomppars
TOI_PLANET = frozenset({"CP", "KP"})  # TFOPWG: confirmed planet, known planet
TOI_FALSE_POSITIVE = frozenset({"FP", "FA"})  # false positive, false alarm


@dataclass(frozen=True)
class CatalogEntry:
    catalog: str  # "pscomppars", "toi" or "ctoi"
    id: str
    period_days: float | None
    disposition: str | None
    url: str


@dataclass(frozen=True)
class MatchedEntry:
    entry: CatalogEntry
    period_match: bool | None
    ratio: str | None  # "1/1", "2/1", "1/3"... when it matches


def period_ratio(
    catalog_period: float, signal_period: float, tolerance: float, max_integer: int
) -> str | None:
    """The ratio catalog/signal as "n/1" or "1/n" when it is an alias within tolerance."""
    for k in range(1, max_integer + 1):
        for ratio, label in ((float(k), f"{k}/1"), (1.0 / k, f"1/{k}")):
            if abs(catalog_period / (signal_period * ratio) - 1.0) <= tolerance:
                return label
    return None


def match_entries(
    entries: Sequence[CatalogEntry],
    signal_period: float | None,
    tolerance: float,
    max_integer: int,
) -> list[MatchedEntry]:
    out = []
    for entry in entries:
        if signal_period is None or entry.period_days is None:
            out.append(MatchedEntry(entry, None, None))
            continue
        ratio = period_ratio(entry.period_days, signal_period, tolerance, max_integer)
        out.append(MatchedEntry(entry, ratio is not None, ratio))
    return out


def _kind(entry: CatalogEntry) -> str:
    disposition = (entry.disposition or "").upper()
    if entry.catalog == "pscomppars" or disposition in TOI_PLANET:
        return "known_planet"
    if disposition in TOI_FALSE_POSITIVE:
        return "known_false_positive"
    return "toi" if entry.catalog == "toi" else "ctoi"


# A confirmed planet outranks a false-positive label at the same period, which
# outranks a candidate.
_PRIORITY = ("known_planet", "known_false_positive", "toi", "ctoi")


def catalog_status(matched: Sequence[MatchedEntry]) -> str:
    """Status from the entries that match the signal's period (or all, without a signal)."""
    relevant = [m for m in matched if m.period_match is not False]
    kinds = {_kind(m.entry) for m in relevant}
    return next((k for k in _PRIORITY if k in kinds), "unknown")


def notes(matched: Sequence[MatchedEntry], signal_period: float | None) -> list[str]:
    out = []
    for m in matched:
        if m.period_match is False:
            out.append(
                f"{m.entry.catalog} {m.entry.id} has period {m.entry.period_days:.6g} d, "
                f"which does not match the signal ({signal_period:.6g} d): "
                "the case continues"
            )
        elif m.period_match is None and signal_period is not None:
            out.append(f"{m.entry.catalog} {m.entry.id} has no period to compare")
    if signal_period is None:
        out.append("no detected signal: the status considers every entry of the star")
    return out
