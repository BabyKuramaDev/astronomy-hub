"""Synthetic sectors for the vetting controls.

Ported from open-exoplanet-hunt tests/test_vetting_controls.py (MIT): three sectors
at 600, 120 and 200 s cadence, a 480 ppm box transit every 3.1828 d, white noise,
and optional odd-even depths, a secondary eclipse, a missing sector, a centroid
shift or a sinusoidal modulation.
"""

from dataclasses import replace

import numpy as np

from contexts.vetting.domain.inputs import GateInputs, MeasureParams, RawSector
from shared.contracts import Measurement
from shared.mission import load_mission

PERIOD = 3.1828
T0 = 1468.42
DURATION_DAYS = 0.072
SECTORS = ((6, 1468.0, 1493.0, 600.0), (32, 2174.0, 2199.0, 120.0), (98, 3990.0, 4015.0, 200.0))
CONFIG = load_mission("exoplanets").vetting
PARAMS = MeasureParams(
    CONFIG.measurement.duration_scale.default,
    CONFIG.measurement.window_durations.default,
    CONFIG.measurement.baseline_inner_durations,
)


def make_inputs(
    *,
    odd_depth: float = 480e-6,
    even_depth: float = 480e-6,
    sec_depth: float = 0.0,
    drop_last_sector_signal: bool = False,
    centroid_shift_pix: float = 0.0,
    sin_mod_amp: float = 0.0,
    seed: int = 42,
) -> GateInputs:
    rng = np.random.default_rng(seed)
    times, fluxes, errs, sectors, raw = [], [], [], [], []
    for idx, (sector, start, end, cadence_s) in enumerate(SECTORS):
        t = np.arange(start, end, cadence_s / 86400.0)
        sigma = 220e-6 if cadence_s <= 200 else 160e-6
        f = 1.0 + rng.normal(0.0, sigma, t.size)
        dx = rng.normal(0.0, 0.002, t.size)
        dy = rng.normal(0.0, 0.002, t.size)
        epoch = np.round((t - T0) / PERIOD).astype(int)
        phase = (t - T0) - epoch * PERIOD
        in_tr = np.abs(phase) <= 0.5 * DURATION_DAYS
        if not (drop_last_sector_signal and idx == 2):
            f[in_tr & (epoch % 2 == 1)] -= odd_depth
            f[in_tr & (epoch % 2 == 0)] -= even_depth
            dx[in_tr] += centroid_shift_pix
        if sec_depth > 0:
            ph_sec = ((t - (T0 + 0.5 * PERIOD) + 0.5 * PERIOD) % PERIOD) - 0.5 * PERIOD
            f[np.abs(ph_sec) <= 0.5 * DURATION_DAYS] -= sec_depth
        if sin_mod_amp > 0:
            f += sin_mod_amp * np.sin(2.0 * np.pi * t / PERIOD)
        times.append(t)
        fluxes.append(f)
        errs.append(np.full(t.size, sigma))
        sectors.append(np.full(t.size, sector))
        raw.append(RawSector(sector, t, f.copy(), 1000.0 + dx, 1000.0 + dy))
    return GateInputs(
        period_days=PERIOD,
        epoch_btjd=T0,
        duration_hours=DURATION_DAYS * 24.0,
        depth_ppm=0.5 * (odd_depth + even_depth) * 1e6,
        snr=20.0,
        snr_min=8.0,
        inverted_snr_max=10.0,
        time=np.concatenate(times),
        flux=np.concatenate(fluxes),
        flux_err=np.concatenate(errs),
        sector=np.concatenate(sectors),
        raw=tuple(raw),
        stellar_radius=Measurement(value=0.65, err_lower=0.02, err_upper=0.02),
        stellar_mass=Measurement(value=0.63, err_lower=0.02, err_upper=0.02),
        model=None,
        catalog=None,
    )


def with_flux(
    inputs: GateInputs, flux: np.ndarray, raw_flux: np.ndarray | None = None
) -> GateInputs:
    """Replace the clean flux and the raw flux of every sector (by default, the same)."""
    raw_flux = flux if raw_flux is None else raw_flux
    parts, start = [], 0
    for sector in inputs.raw:
        stop = start + sector.time.size
        parts.append(replace(sector, flux=raw_flux[start:stop].copy()))
        start = stop
    return replace(inputs, flux=flux, raw=tuple(parts))
