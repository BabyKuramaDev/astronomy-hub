"""Fold a light curve on a period and summarize it numerically for a text reader."""

from dataclasses import dataclass

import numpy as np

from shared.kernel.transits import (
    TransitDepths,
    epoch_index,
    odd_even,
    phase_days,
    robust_std,
    transit_depths,
)


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
    odd_even_diff_ppm: float | None
    odd_even_sigma: float | None

    @property
    def odd_even_difference(self) -> tuple[float | None, float | None]:
        """(odd - even in ppm, |difference| in sigma); each group's error comes from itself."""
        return self.odd_even_diff_ppm, self.odd_even_sigma


def _depth(flux: np.ndarray, baseline: float, scatter: float | None) -> Depth:
    if flux.size == 0:
        return Depth(None, None, 0)
    err = scatter / np.sqrt(flux.size) * 1e6 if scatter is not None else None
    return Depth(float((baseline - flux.mean()) * 1e6), err, int(flux.size))


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
    phase = phase_days(time, period_days, epoch_btjd)
    epochs = epoch_index(time, period_days, epoch_btjd)

    out = np.abs(phase) > duration  # more than one duration from mid-transit
    scatter = robust_std(flux[out])
    baseline = float(np.median(flux[out])) if out.any() else 1.0

    in_transit = np.abs(phase) < 0.5 * duration
    core = np.abs(phase) < 0.25 * duration  # central half: depth without ingress/egress
    split = odd_even(flux, epochs, core, baseline, min_points)

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
        epoch_index=epochs[window],
        n_points=int(time.size),
        n_transits_covered=int(np.unique(epochs[in_transit]).size),
        in_transit=transit_depths(flux[core], epochs[core], baseline, min_points),
        odd=split.odd,
        even=split.even,
        odd_even_diff_ppm=split.difference_ppm,
        odd_even_sigma=split.difference_sigma,
        oot_scatter_ppm=scatter * 1e6 if scatter is not None else None,
        bins=tuple(bins),
    )
