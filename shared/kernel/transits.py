"""Per-transit photometry shared by detection (fold) and vetting (odd-even gate).

Pure numpy, no I/O. Depths are measured transit by transit and their error
comes from the scatter between transits, not from point-to-point scatter, so a
systematic difference between sectors does not look significant. The odd and
even groups each take their error from their own transits only: mixing them
would inflate the error of an eclipsing binary with alternating depths and hide
the difference.
"""

from dataclasses import dataclass

import numpy as np

MAD_TO_SIGMA = 1.4826


def phase_days(time: np.ndarray, period: float, epoch: float) -> np.ndarray:
    """Time from the nearest mid-transit, in days, in [-period/2, period/2)."""
    return (time - epoch + 0.5 * period) % period - 0.5 * period


def epoch_index(time: np.ndarray, period: float, epoch: float) -> np.ndarray:
    """Number of the nearest transit (0 at `epoch`)."""
    return np.rint((time - epoch) / period).astype(np.int64)


def robust_std(values: np.ndarray) -> float | None:
    if values.size < 2:
        return None
    return float(MAD_TO_SIGMA * np.median(np.abs(values - np.median(values))))


@dataclass(frozen=True)
class TransitDepths:
    """Mean depth over individual transits; the error comes from their scatter."""

    value_ppm: float | None
    err_ppm: float | None
    n_transits: int
    per_transit_ppm: tuple[float, ...] = ()


def transit_depths(
    flux: np.ndarray, epochs: np.ndarray, baseline: float, min_points: int
) -> TransitDepths:
    """Depth of each transit with at least min_points, then mean and standard error."""
    depths = []
    for epoch in np.unique(epochs):
        members = flux[epochs == epoch]
        if members.size >= min_points:
            depths.append(float((baseline - members.mean()) * 1e6))
    if not depths:
        return TransitDepths(None, None, 0)
    values = np.array(depths)
    err = float(values.std(ddof=1) / np.sqrt(values.size)) if values.size >= 2 else None
    return TransitDepths(float(values.mean()), err, int(values.size), tuple(depths))


@dataclass(frozen=True)
class OddEvenResult:
    odd: TransitDepths
    even: TransitDepths
    difference_ppm: float | None
    difference_sigma: float | None


def odd_even(
    flux: np.ndarray,
    epochs: np.ndarray,
    in_core: np.ndarray,
    baseline: float,
    min_points: int,
) -> OddEvenResult:
    """Odd and even depths, each with the error of its own group, and their difference."""
    odd_mask = in_core & (epochs % 2 == 1)
    even_mask = in_core & (epochs % 2 == 0)
    odd = transit_depths(flux[odd_mask], epochs[odd_mask], baseline, min_points)
    even = transit_depths(flux[even_mask], epochs[even_mask], baseline, min_points)
    if None in (odd.value_ppm, even.value_ppm, odd.err_ppm, even.err_ppm):
        return OddEvenResult(odd, even, None, None)
    diff = odd.value_ppm - even.value_ppm  # type: ignore[operator]
    err = float(np.hypot(odd.err_ppm, even.err_ppm))  # type: ignore[arg-type]
    return OddEvenResult(odd, even, diff, abs(diff) / err if err > 0 else None)
