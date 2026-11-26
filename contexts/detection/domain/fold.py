"""Fold a light curve on a period and summarize it numerically for a text reader."""

from dataclasses import dataclass
from functools import partial

import numpy as np

MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class Bin:
    phase_hours: float
    depth_ppm: float | None
    depth_err_ppm: float | None
    n_points: int


@dataclass(frozen=True)
class Depth:
    value_ppm: float | None
    err_ppm: float | None
    n_points: int


@dataclass(frozen=True)
class TransitDepths:
    """Mean depth over individual transits; the error comes from their scatter."""

    value_ppm: float | None
    err_ppm: float | None
    n_transits: int


@dataclass(frozen=True)
class FoldResult:
    phase_hours: np.ndarray  # points inside the window, for the data file and figure
    flux: np.ndarray
    epoch_index: np.ndarray
    n_points: int
    n_transits_covered: int
    in_transit: TransitDepths
    odd: TransitDepths
    even: TransitDepths
    oot_scatter_ppm: float | None
    bins: tuple[Bin, ...]

    @property
    def odd_even_difference(self) -> tuple[float | None, float | None]:
        """(odd - even in ppm, |difference| in sigma)."""
        if None in (self.odd.value_ppm, self.even.value_ppm, self.odd.err_ppm, self.even.err_ppm):
            return None, None
        diff = self.odd.value_ppm - self.even.value_ppm  # type: ignore[operator]
        err = float(np.hypot(self.odd.err_ppm, self.even.err_ppm))  # type: ignore[arg-type]
        return diff, (abs(diff) / err if err > 0 else None)


def _robust_std(values: np.ndarray) -> float | None:
    if values.size < 2:
        return None
    return float(MAD_TO_SIGMA * np.median(np.abs(values - np.median(values))))


def _depth(flux: np.ndarray, baseline: float, scatter: float | None) -> Depth:
    if flux.size == 0:
        return Depth(None, None, 0)
    err = scatter / np.sqrt(flux.size) * 1e6 if scatter is not None else None
    return Depth(float((baseline - flux.mean()) * 1e6), err, int(flux.size))


def transit_depths(
    flux: np.ndarray, epoch_index: np.ndarray, baseline: float, min_points: int
) -> TransitDepths:
    """Depth of each transit with at least min_points, then mean and standard error."""
    depths = []
    for epoch in np.unique(epoch_index):
        members = flux[epoch_index == epoch]
        if members.size >= min_points:
            depths.append((baseline - members.mean()) * 1e6)
    if not depths:
        return TransitDepths(None, None, 0)
    values = np.array(depths)
    err = float(values.std(ddof=1) / np.sqrt(values.size)) if values.size >= 2 else None
    return TransitDepths(float(values.mean()), err, int(values.size))


def fold(
    time: np.ndarray,
    flux: np.ndarray,
    *,
    period_days: float,
    epoch_btjd: float,
    duration_hours: float,
    window_durations: float,
    n_bins: int,
    min_points: int = 3,
) -> FoldResult:
    duration = duration_hours / 24.0
    phase = (time - epoch_btjd + 0.5 * period_days) % period_days - 0.5 * period_days
    epoch_index = np.rint((time - epoch_btjd) / period_days).astype(np.int64)

    out = np.abs(phase) > duration  # more than one duration from mid-transit
    scatter = _robust_std(flux[out])
    baseline = float(np.median(flux[out])) if out.any() else 1.0

    in_transit = np.abs(phase) < 0.5 * duration
    core = np.abs(phase) < 0.25 * duration  # central half: depth without ingress/egress
    odd = core & (epoch_index % 2 == 1)
    even = core & (epoch_index % 2 == 0)
    per_transit = partial(transit_depths, baseline=baseline, min_points=min_points)

    half_window = window_durations * duration
    edges = np.linspace(-half_window, half_window, n_bins + 1)
    which = np.digitize(phase, edges) - 1
    bins = []
    for k in range(n_bins):
        members = flux[which == k]
        depth = _depth(members, baseline, scatter)
        bins.append(
            Bin(
                phase_hours=float(0.5 * (edges[k] + edges[k + 1]) * 24.0),
                depth_ppm=depth.value_ppm,
                depth_err_ppm=depth.err_ppm,
                n_points=depth.n_points,
            )
        )

    window = np.abs(phase) <= half_window
    return FoldResult(
        phase_hours=phase[window] * 24.0,
        flux=flux[window],
        epoch_index=epoch_index[window],
        n_points=int(time.size),
        n_transits_covered=int(np.unique(epoch_index[in_transit]).size),
        in_transit=per_transit(flux[core], epoch_index[core]),
        odd=per_transit(flux[odd], epoch_index[odd]),
        even=per_transit(flux[even], epoch_index[even]),
        oot_scatter_ppm=scatter * 1e6 if scatter is not None else None,
        bins=tuple(bins),
    )
