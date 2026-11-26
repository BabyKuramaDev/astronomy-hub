"""Box least squares period search and peak triage.

The SNR of a peak is depth / depth_err from astropy's BLS: a white-noise SNR.
"""

import math
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from fractions import Fraction

import numpy as np
from astropy.timeseries import BoxLeastSquares


class SearchError(ValueError):
    """The light curve cannot be searched with the given parameters."""


@dataclass(frozen=True)
class SearchParams:
    period_min_days: float
    period_max_days: float
    durations_hours: tuple[float, ...]
    bin_minutes: float
    frequency_factor: float
    n_peaks: int
    examine_factor: int  # distinct peaks examined at most, as a multiple of n_peaks
    peak_separation: float
    harmonic_max_integer: int
    harmonic_tolerance: float
    min_transits: int


@dataclass(frozen=True)
class Candidate:
    period_days: float
    epoch_btjd: float
    duration_hours: float
    depth_ppm: float
    snr: float
    power: float
    n_transits: int = 0


@dataclass(frozen=True)
class Discarded:
    candidate: Candidate
    reason: str  # "non_positive_depth" | "harmonic"
    harmonic_of: int | None = None  # index into SearchOutcome.peaks
    ratio: Fraction | None = None


@dataclass(frozen=True)
class SearchOutcome:
    period_min_days: float
    period_max_days: float
    durations_hours: tuple[float, ...]
    n_periods: int
    peaks: tuple[Candidate, ...]
    discarded: tuple[Discarded, ...]


def bin_lightcurve(
    time: np.ndarray, flux: np.ndarray, flux_err: np.ndarray, bin_minutes: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Average into fixed time bins; empty bins are dropped."""
    width = bin_minutes / 1440.0
    index = np.floor((time - time.min()) / width).astype(np.int64)
    _, inverse, counts = np.unique(index, return_inverse=True, return_counts=True)
    t = np.bincount(inverse, weights=time) / counts
    f = np.bincount(inverse, weights=flux) / counts
    e = np.sqrt(np.bincount(inverse, weights=flux_err**2)) / counts
    return t, f, e


def harmonic_ratio(
    period: float, reference: float, max_integer: int, tol: float
) -> Fraction | None:
    """The ratio period / reference as an alias of the reference peak, or None.

    Candidates are any integer multiple k or submultiple 1/k (a multiple covers a
    subset of the same transits), and fractions n/m with n, m <= max_integer.
    1/1 is never a harmonic. The closest candidate within the relative tolerance wins.
    """
    value = period / reference
    candidates = {
        Fraction(n, m)
        for n in range(1, max_integer + 1)
        for m in range(1, max_integer + 1)
        if n != m
    }
    k = round(value) if value >= 1 else round(1 / value)
    if k > 1:
        candidates.add(Fraction(k) if value >= 1 else Fraction(1, k))
    matches = [f for f in candidates if abs(value / float(f) - 1.0) <= tol]
    return min(matches, key=lambda f: (abs(value / float(f) - 1.0), f), default=None)


def first_epoch(epoch: float, period: float, t_start: float) -> float:
    """The first transit time at or after the start of the data."""
    return epoch + period * math.ceil((t_start - epoch) / period)


def triage(
    ranked: Iterable[tuple[Candidate, float]],
    params: SearchParams,
    count_transits: Callable[[Candidate, float], int],
) -> tuple[tuple[Candidate, ...], tuple[Discarded, ...]]:
    """Walk candidates in power order and sort them into kept peaks and discarded ones.

    Candidates closer than peak_separation to one already seen are the same peak.
    A distinct candidate is discarded if its depth is not positive, or if its period
    is an integer ratio of a kept peak's period; otherwise it is kept.
    """
    peaks: list[Candidate] = []
    discarded: list[Discarded] = []
    seen: list[float] = []
    examined = 0
    for candidate, transit_time in ranked:
        if len(peaks) >= params.n_peaks or examined >= params.examine_factor * params.n_peaks:
            break
        period = candidate.period_days
        if any(abs(period - p) / p <= params.peak_separation for p in seen):
            continue
        seen.append(period)
        examined += 1
        if candidate.depth_ppm <= 0:
            discarded.append(Discarded(candidate, "non_positive_depth"))
            continue
        harmonic = None
        for k, kept in enumerate(peaks):
            ratio = harmonic_ratio(
                period, kept.period_days, params.harmonic_max_integer, params.harmonic_tolerance
            )
            if ratio is not None:
                harmonic = (k, ratio)
                break
        if harmonic is not None:
            discarded.append(Discarded(candidate, "harmonic", harmonic[0], harmonic[1]))
            continue
        peaks.append(replace(candidate, n_transits=count_transits(candidate, transit_time)))
    return tuple(peaks), tuple(discarded)


def search_periods(
    time: np.ndarray, flux: np.ndarray, flux_err: np.ndarray, params: SearchParams
) -> SearchOutcome:
    if time.size < 10:
        raise SearchError("too few points to search")
    t, f, e = bin_lightcurve(time, flux, flux_err, params.bin_minutes)
    baseline = float(t.max() - t.min())
    period_max = params.period_max_days
    if params.min_transits > 1:
        period_max = min(period_max, baseline / (params.min_transits - 1))
    if period_max <= params.period_min_days:
        raise SearchError(
            f"baseline of {baseline:.2f} d is too short for {params.min_transits} transits "
            f"above {params.period_min_days} d"
        )
    durations = tuple(d for d in params.durations_hours if d / 24.0 < params.period_min_days)
    if not durations:
        raise SearchError("every duration is longer than period_min_days")

    bls = BoxLeastSquares(t, f, dy=e)
    durations_days = np.array(durations) / 24.0
    periods = bls.autoperiod(
        durations_days,
        minimum_period=params.period_min_days,
        maximum_period=period_max,
        frequency_factor=params.frequency_factor,
    )
    result = bls.power(periods, durations_days, objective="likelihood")
    power = np.asarray(result.power)
    order = np.lexsort((np.arange(power.size), -power))

    def ranked() -> Iterator[tuple[Candidate, float]]:
        for i in order:
            period = float(periods[i])
            yield (
                Candidate(
                    period_days=period,
                    epoch_btjd=first_epoch(float(result.transit_time[i]), period, float(t.min())),
                    duration_hours=float(result.duration[i]) * 24.0,
                    depth_ppm=float(result.depth[i]) * 1e6,
                    snr=float(result.depth_snr[i]),
                    power=float(power[i]),
                ),
                float(result.transit_time[i]),
            )

    def count_transits(candidate: Candidate, transit_time: float) -> int:
        stats = bls.compute_stats(
            candidate.period_days, candidate.duration_hours / 24.0, transit_time
        )
        return int(np.count_nonzero(np.asarray(stats["per_transit_count"]) > 0))

    peaks, discarded = triage(ranked(), params, count_transits)
    return SearchOutcome(
        period_min_days=params.period_min_days,
        period_max_days=period_max,
        durations_hours=durations,
        n_periods=int(periods.size),
        peaks=peaks,
        discarded=discarded,
    )
