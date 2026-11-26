"""Transit model (batman, quadratic limb darkening) and its posterior for emcee.

Parameters: t0, period, rp_rs, b, log_a_rs, q1, q2, f0, log_jitter. Limb darkening
uses the Kipping (2013) q1, q2 parametrization with uniform priors on [0, 1], so no
tabulated coefficients enter the fit. The jitter is white noise added in quadrature
to every point's error; its log has a uniform prior between the bounds.
"""

import math
from dataclasses import dataclass

import batman
import numpy as np

PARAMS = ("t0", "period", "rp_rs", "b", "log_a_rs", "q1", "q2", "f0", "log_jitter")
NDIM = len(PARAMS)


@dataclass(frozen=True)
class Bounds:
    t0: tuple[float, float]
    period: tuple[float, float]
    log_a_rs: tuple[float, float] = (0.0, math.log(500.0))
    f0: tuple[float, float] = (0.98, 1.02)
    log_jitter: tuple[float, float] = (math.log(1e-9), math.log(0.05))


@dataclass(frozen=True)
class Guess:
    t0: float
    period: float
    duration_days: float
    depth: float  # fractional


def limb_darkening(q1: float, q2: float) -> tuple[float, float]:
    sq = math.sqrt(q1)
    return 2.0 * sq * q2, sq * (1.0 - 2.0 * q2)


def initial_vector(guess: Guess) -> np.ndarray:
    rp = math.sqrt(max(guess.depth, 1e-6))
    b = 0.3
    chord = math.sqrt(max((1.0 + rp) ** 2 - b**2, 1e-3))
    a = max(guess.period / (math.pi * guess.duration_days) * chord, 1.0 + rp + 0.1)
    return np.array([guess.t0, guess.period, rp, b, math.log(a), 0.5, 0.5, 1.0, math.log(1e-5)])


class TransitPosterior:
    def __init__(
        self,
        time: np.ndarray,
        flux: np.ndarray,
        flux_err: np.ndarray,
        bounds: Bounds,
        start: np.ndarray,
    ) -> None:
        self.time = time
        self.flux = flux
        self.var = flux_err**2
        self.bounds = bounds
        self._params = batman.TransitParams()
        self._set(start)
        self._model = batman.TransitModel(self._params, time)

    def _set(self, theta: np.ndarray) -> None:
        t0, period, rp, b, log_a, q1, q2 = theta[:7]
        a = math.exp(log_a)
        p = self._params
        p.t0, p.per, p.rp, p.a = t0, period, rp, a
        p.inc = math.degrees(math.acos(b / a))
        p.ecc, p.w = 0.0, 90.0
        p.u = list(limb_darkening(q1, q2))
        p.limb_dark = "quadratic"

    def in_bounds(self, theta: np.ndarray) -> bool:
        t0, period, rp, b, log_a, q1, q2, f0, log_jitter = theta
        bd = self.bounds
        return (
            bd.t0[0] < t0 < bd.t0[1]
            and bd.period[0] < period < bd.period[1]
            and 0.0 < rp < 1.0
            and 0.0 <= b < 1.0 + rp
            and bd.log_a_rs[0] < log_a < bd.log_a_rs[1]
            and math.exp(log_a) > 1.0 + rp
            and 0.0 <= q1 <= 1.0
            and 0.0 <= q2 <= 1.0
            and bd.f0[0] < f0 < bd.f0[1]
            and bd.log_jitter[0] < log_jitter < bd.log_jitter[1]
        )

    def model(self, theta: np.ndarray) -> np.ndarray:
        self._set(theta)
        return theta[7] * self._model.light_curve(self._params)

    def __call__(self, theta: np.ndarray) -> float:
        if not self.in_bounds(theta):
            return -math.inf
        resid = self.flux - self.model(theta)
        var = self.var + math.exp(2.0 * theta[8])
        value = -0.5 * float(np.sum(resid * resid / var + np.log(var)))
        return value if math.isfinite(value) else -math.inf


def total_duration_days(
    period: np.ndarray, rp_rs: np.ndarray, b: np.ndarray, a_rs: np.ndarray
) -> np.ndarray:
    """T14 of a circular orbit; NaN where the planet does not transit."""
    with np.errstate(invalid="ignore", divide="ignore"):
        sin_i = np.sqrt(1.0 - (b / a_rs) ** 2)
        chord = np.sqrt((1.0 + rp_rs) ** 2 - b**2) / (a_rs * sin_i)
        return np.where(chord <= 1.0, period / math.pi * np.arcsin(chord), np.nan)
