"""The independent analysis: another cleaning and another search (TLS).

It never sees signal.json: it starts from the raw per-sector tables, detrends with
a running median (preparation uses a biweight) and searches with Transit Least
Squares (detection uses BLS).
"""

import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

MAD_TO_SIGMA = 1.4826


class ReproductionError(ValueError):
    """The light curve cannot be searched with the given parameters."""


@dataclass(frozen=True)
class RawSector:
    sector: int
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray


@dataclass(frozen=True)
class ReproductionParams:
    detrend_method: str
    detrend_window_days: float
    break_tolerance_days: float
    sigma_upper: float
    bin_minutes: float
    period_min_days: float
    period_max_days: float
    min_transits: int
    sde_min: float
    oversampling_factor: int
    duration_grid_step: float
    threads: int


@dataclass(frozen=True)
class Reproduction:
    detected: bool
    period_days: float | None
    epoch_btjd: float | None
    duration_hours: float | None
    depth_ppm: float | None
    sde: float | None
    snr: float | None
    n_transits: int | None
    period_max_days: float
    warnings: tuple[str, ...] = ()


def clean(sectors: Sequence[RawSector], params: ReproductionParams) -> tuple[np.ndarray, ...]:
    """Normalize each sector, detrend it with a running median and clip upward outliers."""
    from wotan import flatten  # see preparation: numba binds its cache dir at decoration

    parts = []
    for s in sorted(sectors, key=lambda x: x.sector):
        order = np.argsort(s.time, kind="stable")
        t, f, e = s.time[order], s.flux[order], s.flux_err[order]
        median = float(np.median(f))
        if t.size == 0 or not np.isfinite(median) or median <= 0:
            continue
        f, e = f / median, e / median
        flat, trend = flatten(
            t,
            f,
            method=params.detrend_method,
            window_length=params.detrend_window_days,
            break_tolerance=params.break_tolerance_days,
            edge_cutoff=0.0,
            return_trend=True,
        )
        ok = np.isfinite(flat) & np.isfinite(trend) & (trend > 0)
        scatter = MAD_TO_SIGMA * np.median(np.abs(flat[ok] - np.median(flat[ok])))
        ok &= flat <= np.median(flat[ok]) + params.sigma_upper * scatter
        parts.append((t[ok], flat[ok], (e / np.where(trend > 0, trend, 1.0))[ok]))
    if not parts:
        raise ReproductionError("no valid points to search")
    t, f, e = (np.concatenate(cols) for cols in zip(*parts, strict=True))
    order = np.argsort(t, kind="stable")
    return t[order], f[order], e[order]


def bin_series(
    t: np.ndarray, f: np.ndarray, e: np.ndarray, minutes: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    width = minutes / 1440.0
    index = np.floor((t - t.min()) / width).astype(np.int64)
    _, inverse, counts = np.unique(index, return_inverse=True, return_counts=True)
    tb = np.bincount(inverse, weights=t) / counts
    fb = np.bincount(inverse, weights=f) / counts
    eb = np.sqrt(np.bincount(inverse, weights=e**2)) / counts
    return tb, fb, eb


def reproduce(sectors: Sequence[RawSector], params: ReproductionParams) -> Reproduction:
    from transitleastsquares import transitleastsquares  # numba: see clean()

    t, f, e = bin_series(*clean(sectors, params), params.bin_minutes)
    if t.size < 50:
        raise ReproductionError("too few points to search")
    baseline = float(t.max() - t.min())
    period_max = min(params.period_max_days, baseline / max(params.min_transits - 1, 1))
    if period_max <= params.period_min_days:
        raise ReproductionError(
            f"baseline of {baseline:.2f} d is too short for {params.min_transits} transits"
        )
    # TLS reports caveats as Python warnings; they go to the summary, not to stderr.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = transitleastsquares(t, f, e, verbose=False)
        r = model.power(
            period_min=params.period_min_days,
            period_max=period_max,
            n_transits_min=params.min_transits,
            oversampling_factor=params.oversampling_factor,
            duration_grid_step=params.duration_grid_step,
            use_threads=params.threads,
            show_progress_bar=False,
            verbose=False,
        )
    notes = tuple(dict.fromkeys(f"TLS: {w.message}" for w in caught))
    sde = float(r.SDE) if np.isfinite(r.SDE) else None
    detected = sde is not None and sde >= params.sde_min and np.isfinite(r.period)
    if not detected:
        return Reproduction(False, None, None, None, None, sde, None, None, period_max, notes)
    return Reproduction(
        detected=True,
        period_days=float(r.period),
        epoch_btjd=float(r.T0),
        duration_hours=float(r.duration) * 24.0,
        depth_ppm=float((1.0 - r.depth) * 1e6),
        sde=sde,
        snr=float(r.snr) if np.isfinite(r.snr) else 0.0,
        n_transits=int(r.distinct_transit_count),
        period_max_days=period_max,
        warnings=notes,
    )
