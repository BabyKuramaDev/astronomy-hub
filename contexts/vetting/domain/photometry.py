"""Measurements shared by the gates: windows around the transits and weighted dips.

Ported from open-exoplanet-hunt (MIT): the in-transit window is |phase| <= duration / 2
and the local baseline is inner < |phase| / duration < outer, around every transit.
"""

import math
from dataclasses import dataclass

import numpy as np

from contexts.vetting.domain.inputs import GateInputs, MeasureParams
from shared.kernel.transits import epoch_index, phase_days


@dataclass(frozen=True)
class Windows:
    duration_days: float
    phase: np.ndarray
    epochs: np.ndarray
    in_transit: np.ndarray
    baseline: np.ndarray


def windows(
    time: np.ndarray, period: float, epoch: float, duration_days: float, params: MeasureParams
) -> Windows:
    phase = phase_days(time, period, epoch)
    absolute = np.abs(phase)
    return Windows(
        duration_days=duration_days,
        phase=phase,
        epochs=epoch_index(time, period, epoch),
        in_transit=absolute <= 0.5 * duration_days,
        baseline=(absolute > params.baseline_inner_durations * duration_days)
        & (absolute < params.window_durations * duration_days),
    )


def signal_windows(inputs: GateInputs, params: MeasureParams, shift: float = 0.0) -> Windows:
    """Windows on the clean light curve; shift moves the centre by a fraction of the period."""
    duration = inputs.duration_hours / 24.0 * params.duration_scale
    epoch = inputs.epoch_btjd + shift * inputs.period_days
    return windows(inputs.time, inputs.period_days, epoch, duration, params)


@dataclass(frozen=True)
class Dip:
    ppm: float
    err_ppm: float

    @property
    def snr(self) -> float:
        return self.ppm / self.err_ppm if self.err_ppm > 0 else 0.0


def weighted_dip(
    flux: np.ndarray, weights: np.ndarray, inside: np.ndarray, outside: np.ndarray
) -> Dip | None:
    """Baseline minus in-window flux (inverse-variance means), with its white-noise error."""
    if inside.sum() < 1 or outside.sum() < 2:
        return None
    w_in, w_out = weights[inside].sum(), weights[outside].sum()
    mean_in = float(np.sum(weights[inside] * flux[inside]) / w_in)
    mean_out = float(np.sum(weights[outside] * flux[outside]) / w_out)
    return Dip((mean_out - mean_in) * 1e6, math.sqrt(1.0 / w_in + 1.0 / w_out) * 1e6)


@dataclass(frozen=True)
class TransitDip:
    epoch: int
    sector: int
    dip: Dip


def per_transit_dips(
    flux: np.ndarray, weights: np.ndarray, sector: np.ndarray, win: Windows
) -> list[TransitDip]:
    """Dip of every transit with at least one in-transit and two baseline points."""
    out = []
    for ep in np.unique(win.epochs[win.in_transit]):
        mine = win.epochs == ep
        dip = weighted_dip(flux, weights, win.in_transit & mine, win.baseline & mine)
        if dip is not None:
            sectors = sector[win.in_transit & mine]
            out.append(TransitDip(int(ep), int(np.bincount(sectors).argmax()), dip))
    return out


def sinusoid_amplitude(time: np.ndarray, flux: np.ndarray, period: float) -> float:
    """Amplitude of the best sinusoid at `period` (least squares with an offset)."""
    omega = 2.0 * math.pi / period
    design = np.column_stack([np.sin(omega * time), np.cos(omega * time), np.ones(time.size)])
    coeffs, *_ = np.linalg.lstsq(design, flux, rcond=None)
    return float(math.hypot(coeffs[0], coeffs[1]))
