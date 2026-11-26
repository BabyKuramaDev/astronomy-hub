"""Synthetic light curves for offline tests (seeded, nothing stored on disk)."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.io import fits


@dataclass(frozen=True)
class Transit:
    period_days: float
    epoch_btjd: float
    duration_hours: float
    depth_ppm: float


def box_transit(time: np.ndarray, transit: Transit) -> np.ndarray:
    """Relative flux with a trapezoidal dip (10% ingress/egress)."""
    half = transit.duration_hours / 48.0
    ramp = 0.1 * 2 * half
    phase = (time - transit.epoch_btjd + 0.5 * transit.period_days) % transit.period_days
    dt = np.abs(phase - 0.5 * transit.period_days)
    depth = transit.depth_ppm * 1e-6
    shape = np.clip((half - dt) / ramp, 0.0, 1.0)
    return 1.0 - depth * shape


def light_curve(
    *,
    start: float = 1000.0,
    days: float = 20.0,
    cadence_min: float = 2.0,
    noise_ppm: float = 300.0,
    transit: Transit | None = None,
    trend_amplitude: float = 0.0,
    seed: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    time = start + np.arange(0.0, days, cadence_min / 1440.0)
    flux = np.ones_like(time)
    if transit is not None:
        flux = box_transit(time, transit)
    if trend_amplitude:
        flux = flux * (1.0 + trend_amplitude * np.sin(2 * np.pi * (time - start) / 7.3))
    flux = flux + rng.normal(0.0, noise_ppm * 1e-6, time.size)
    err = np.full_like(time, noise_ppm * 1e-6)
    return time, flux, err


def write_spoc_fits(
    path: Path,
    *,
    tic_id: int,
    sector: int,
    time: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    quality: np.ndarray | None = None,
    scale: float = 50000.0,
) -> Path:
    """A minimal SPOC-like light curve file (only the columns the hub reads)."""
    quality = np.zeros(time.size, dtype=np.int32) if quality is None else quality
    primary = fits.PrimaryHDU()
    primary.header["TELESCOP"] = "TESS"
    primary.header["SECTOR"] = sector
    primary.header["TICID"] = tic_id
    table = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="TIME", format="D", array=time),
            fits.Column(name="PDCSAP_FLUX", format="E", array=(flux * scale).astype(np.float32)),
            fits.Column(
                name="PDCSAP_FLUX_ERR", format="E", array=(flux_err * scale).astype(np.float32)
            ),
            fits.Column(name="QUALITY", format="J", array=quality.astype(np.int32)),
        ],
        name="LIGHTCURVE",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList([primary, table]).writeto(path, overwrite=True)
    return path
