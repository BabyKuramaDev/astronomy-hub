"""Box least squares period search and peak triage.

The SNR of a peak is depth / depth_err from astropy's BLS: a white-noise SNR.
The same search on the inverted light curve, where every dip is noise, gives the
noise floor of the star (its maximum SNR). Each peak also carries its SDE, the
signal detection efficiency of the periodogram, as data for later calibration.

The durations tried at each period are limited to what is physically possible:
the longest central transit of a planet with radius ratio rp_rs_max around a star
of density stellar_density_min_solar, from Kepler's third law, times
eccentricity_factor (a transit near apoastron lasts longer than a circular one). The
caller passes the star's own density when the TIC has it.
"""

import math
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from fractions import Fraction

import numpy as np
from astropy import constants
from astropy.timeseries import BoxLeastSquares

SOLAR_DENSITY_KG_M3 = float(
    (constants.M_sun / (4.0 / 3.0 * math.pi * constants.R_sun**3)).to_value("kg / m3")
)
G_SI = float(constants.G.to_value("m3 / (kg s2)"))
SECONDS_PER_DAY = 86400.0


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
    stellar_density_min_solar: float
    rp_rs_max: float
    floor_mask_durations: float  # half-width masked around the top peak's transits
    eccentricity_factor: float = 1.0  # margin over the circular maximum duration


@dataclass(frozen=True)
class Candidate:
    period_days: float
    epoch_btjd: float
    duration_hours: float
    depth_ppm: float
    snr: float
    power: float
    sde: float = 0.0
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
    inverted_snr_max: float


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


def max_duration_days(
    period_days: np.ndarray | float, density_min_solar: float, rp_rs_max: float
) -> np.ndarray:
    """Longest possible transit (b = 0, circular orbit) at each period.

    a/R* = (G rho P^2 / (3 pi))^(1/3) from Kepler's third law with M* = 4/3 pi rho R*^3;
    T_max = (P / pi) asin(min(1, (1 + k) R*/a)).
    """
    period = np.asarray(period_days, dtype=float)
    rho = density_min_solar * SOLAR_DENSITY_KG_M3
    p_s = period * SECONDS_PER_DAY
    a_rs = np.cbrt(G_SI * rho * p_s**2 / (3.0 * math.pi))
    return period / math.pi * np.arcsin(np.minimum(1.0, (1.0 + rp_rs_max) / a_rs))


@dataclass(frozen=True)
class Periodogram:
    periods: np.ndarray
    power: np.ndarray
    depth: np.ndarray
    snr: np.ndarray
    duration: np.ndarray
    transit_time: np.ndarray


def run_bls(
    bls: BoxLeastSquares, periods: np.ndarray, durations_days: np.ndarray, params: SearchParams
) -> Periodogram:
    """BLS over the period grid; each period only tries durations below T_max(P).

    T_max grows with the period, so the grid splits into contiguous stretches that share
    the same set of allowed durations; periods where no duration is allowed are dropped.
    """
    limit = params.eccentricity_factor * max_duration_days(
        periods, params.stellar_density_min_solar, params.rp_rs_max
    )
    n_allowed = np.searchsorted(np.sort(durations_days), limit, side="right")
    durations = np.sort(durations_days)
    parts: dict[str, list[np.ndarray]] = {k: [] for k in Periodogram.__dataclass_fields__}
    start = 0
    while start < periods.size:
        stop = start
        while stop < periods.size and n_allowed[stop] == n_allowed[start]:
            stop += 1
        if n_allowed[start] > 0:
            chunk = periods[start:stop]
            r = bls.power(chunk, durations[: n_allowed[start]], objective="likelihood")
            parts["periods"].append(chunk)
            parts["power"].append(np.asarray(r.power))
            parts["depth"].append(np.asarray(r.depth))
            parts["snr"].append(np.asarray(r.depth_snr))
            parts["duration"].append(np.asarray(r.duration))
            parts["transit_time"].append(np.asarray(r.transit_time))
        start = stop
    if not parts["periods"]:
        raise SearchError("no duration is physically possible at any searched period")
    return Periodogram(**{k: np.concatenate(v) for k, v in parts.items()})


def sde(power: np.ndarray) -> np.ndarray:
    """Signal detection efficiency: (power - mean) / std over the periodogram."""
    std = float(np.std(power))
    return (power - float(np.mean(power))) / std if std > 0 else np.zeros_like(power)


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

    durations_days = np.array(durations) / 24.0
    bls = BoxLeastSquares(t, f, dy=e)
    periods = bls.autoperiod(
        durations_days,
        minimum_period=params.period_min_days,
        maximum_period=period_max,
        frequency_factor=params.frequency_factor,
    )
    gram = run_bls(bls, periods, durations_days, params)
    detection_efficiency = sde(gram.power)
    order = np.lexsort((np.arange(gram.power.size), -gram.power))

    def ranked() -> Iterator[tuple[Candidate, float]]:
        for i in order:
            period = float(gram.periods[i])
            yield (
                Candidate(
                    period_days=period,
                    epoch_btjd=first_epoch(float(gram.transit_time[i]), period, float(t.min())),
                    duration_hours=float(gram.duration[i]) * 24.0,
                    depth_ppm=float(gram.depth[i]) * 1e6,
                    snr=float(gram.snr[i]),
                    power=float(gram.power[i]),
                    sde=float(detection_efficiency[i]),
                ),
                float(gram.transit_time[i]),
            )

    def count_transits(candidate: Candidate, transit_time: float) -> int:
        stats = bls.compute_stats(
            candidate.period_days, candidate.duration_hours / 24.0, transit_time
        )
        return int(np.count_nonzero(np.asarray(stats["per_transit_count"]) > 0))

    peaks, discarded = triage(ranked(), params, count_transits)

    # Noise floor: the same search on the inverted curve, where any dip is noise. The
    # transits of the strongest peak are masked first: inverted, they become bumps that
    # raise the out-of-box mean and make every box elsewhere look like a dip.
    keep = np.ones(t.size, dtype=bool)
    if peaks:
        top = peaks[0]
        phase = (t - top.epoch_btjd + 0.5 * top.period_days) % top.period_days
        keep = (
            np.abs(phase - 0.5 * top.period_days)
            > params.floor_mask_durations * top.duration_hours / 24.0
        )
    if keep.sum() < 10:
        raise SearchError("too few points left to estimate the noise floor")
    inverted = run_bls(
        BoxLeastSquares(t[keep], 2.0 - f[keep], dy=e[keep]), periods, durations_days, params
    )
    positive = inverted.depth > 0
    floor = float(np.max(inverted.snr[positive])) if positive.any() else 0.0
    return SearchOutcome(
        period_min_days=params.period_min_days,
        period_max_days=period_max,
        durations_hours=durations,
        n_periods=int(gram.periods.size),
        peaks=peaks,
        discarded=discarded,
        inverted_snr_max=max(floor, 0.0),
    )
