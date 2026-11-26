"""Clean a multi-sector light curve: normalize, detrend, clip upward outliers, stitch."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class SectorSeries:
    sector: int
    time_btjd: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray


@dataclass(frozen=True)
class SectorStats:
    sector: int
    n_in: int
    n_out: int
    n_edge: int
    n_clipped: int


@dataclass(frozen=True)
class CleanLightcurve:
    time_btjd: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    sector: np.ndarray
    stats: tuple[SectorStats, ...]


def robust_std(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(MAD_TO_SIGMA * np.median(np.abs(values - np.median(values))))


def normalize(series: SectorSeries) -> SectorSeries:
    median = float(np.median(series.flux))
    if not np.isfinite(median) or median <= 0:
        raise ValueError(f"sector {series.sector}: median flux is not positive")
    return SectorSeries(
        series.sector, series.time_btjd, series.flux / median, series.flux_err / median
    )


def detrend(
    time: np.ndarray, flux: np.ndarray, window_days: float, break_tolerance_days: float
) -> tuple[np.ndarray, np.ndarray]:
    # Imported here, not at module level: numba binds its cache directory when wotan's
    # kernels are decorated, and the tool sets NUMBA_CACHE_DIR (isolated_caches) first.
    from wotan import flatten

    flat, trend = flatten(
        time,
        flux,
        method="biweight",
        window_length=window_days,
        break_tolerance=break_tolerance_days,
        edge_cutoff=0.0,
        return_trend=True,
    )
    return np.asarray(flat, dtype=np.float64), np.asarray(trend, dtype=np.float64)


def upper_outliers(flux: np.ndarray, sigma_upper: float) -> np.ndarray:
    """Mask of points above median + sigma_upper * robust std. Dips are never clipped."""
    limit = np.median(flux) + sigma_upper * robust_std(flux)
    return flux > limit


def clean_sectors(
    sectors: Sequence[SectorSeries],
    *,
    window_days: float,
    break_tolerance_days: float,
    sigma_upper: float,
) -> CleanLightcurve:
    parts: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    stats = []
    for raw in sorted(sectors, key=lambda s: s.sector):
        order = np.argsort(raw.time_btjd, kind="stable")
        series = SectorSeries(
            raw.sector, raw.time_btjd[order], raw.flux[order], raw.flux_err[order]
        )
        if series.time_btjd.size == 0:
            stats.append(SectorStats(raw.sector, 0, 0, 0, 0))
            continue
        series = normalize(series)
        flat, trend = detrend(series.time_btjd, series.flux, window_days, break_tolerance_days)
        finite = np.isfinite(flat) & np.isfinite(trend) & (trend > 0)
        clipped = np.zeros_like(finite)
        clipped[finite] = upper_outliers(flat[finite], sigma_upper)
        keep = finite & ~clipped
        parts.append(
            (
                series.time_btjd[keep],
                flat[keep],
                (series.flux_err / np.where(trend > 0, trend, 1.0))[keep],
                np.full(int(keep.sum()), raw.sector, dtype=np.int16),
            )
        )
        stats.append(
            SectorStats(
                sector=raw.sector,
                n_in=int(series.time_btjd.size),
                n_out=int(keep.sum()),
                n_edge=int((~finite).sum()),
                n_clipped=int(clipped.sum()),
            )
        )
    if not parts:
        empty = np.array([], dtype=np.float64)
        return CleanLightcurve(empty, empty, empty, np.array([], dtype=np.int16), tuple(stats))
    time, flux, err, sector = (np.concatenate(cols) for cols in zip(*parts, strict=True))
    order = np.argsort(time, kind="stable")
    return CleanLightcurve(time[order], flux[order], err[order], sector[order], tuple(stats))
