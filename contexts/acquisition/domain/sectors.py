"""Deterministic choice of TESS sectors (mission.yaml: sector_selection)."""

from collections.abc import Iterable


def consecutive_runs(sectors: Iterable[int]) -> list[list[int]]:
    ordered = sorted(set(sectors))
    runs: list[list[int]] = []
    for sector in ordered:
        if runs and sector == runs[-1][-1] + 1:
            runs[-1].append(sector)
        else:
            runs.append([sector])
    return runs


def select_sectors(available: Iterable[int], max_sectors: int) -> list[int]:
    """Rule longest_consecutive_run.

    Take the longest run of consecutive sector numbers (ties: the most recent run)
    and, if it is longer than max_sectors, keep its most recent max_sectors.
    Sectors from other runs are never added.
    """
    if max_sectors < 1:
        raise ValueError("max_sectors must be positive")
    runs = consecutive_runs(available)
    if not runs:
        return []
    best = max(runs, key=lambda run: (len(run), run[-1]))
    return best[-max_sectors:]
