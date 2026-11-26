"""MCMC fit of a transit with emcee: fixed seed, posterior summaries, convergence."""

import math
from dataclasses import dataclass

import emcee
import numpy as np
from astropy import constants

from contexts.modeling.domain.transit import NDIM, Bounds, Guess, TransitPosterior, initial_vector
from shared.contracts import Measurement

RSUN_IN_REARTH = float((constants.R_sun / constants.R_earth).decompose().value)


class FitError(ValueError):
    """The fit cannot run with the given data or settings."""


@dataclass(frozen=True)
class ChainSettings:
    walkers: int
    steps: int
    burn: int
    seed: int
    autocorr_factor: float


@dataclass(frozen=True)
class Convergence:
    tau_max: float | None
    n_post_burn: int
    autocorr_factor: float
    converged: bool
    acceptance_mean: float
    acceptance_min: float


@dataclass(frozen=True)
class FitResult:
    rp_rs: Measurement
    impact_parameter: Measurement
    a_rs: Measurement
    t0: Measurement
    period: Measurement
    rp_rs_samples: np.ndarray
    convergence: Convergence
    n_points: int


def summarize(samples: np.ndarray) -> Measurement:
    p16, p50, p84 = np.percentile(samples, [16, 50, 84])
    return Measurement(value=float(p50), err_lower=float(p50 - p16), err_upper=float(p84 - p50))


def transit_window(time: np.ndarray, t0: float, period: float, half_width: float) -> np.ndarray:
    phase = (time - t0 + 0.5 * period) % period - 0.5 * period
    return np.abs(phase) <= half_width


def fit_transit(
    time: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    guess: Guess,
    settings: ChainSettings,
    window_durations: float,
) -> FitResult:
    if settings.walkers < 2 * NDIM:
        raise FitError(f"walkers must be at least {2 * NDIM} for {NDIM} parameters")
    if settings.burn >= settings.steps:
        raise FitError("burn must be below steps")
    keep = transit_window(time, guess.t0, guess.period, window_durations * guess.duration_days)
    t, f, e = time[keep], flux[keep], flux_err[keep]
    if t.size < 10 * NDIM:
        raise FitError(f"only {t.size} points near the transits")

    # Reference epoch near the middle of the data decorrelates t0 and period.
    mid = 0.5 * (t.min() + t.max())
    t0 = guess.t0 + guess.period * round((mid - guess.t0) / guess.period)
    guess = Guess(t0, guess.period, guess.duration_days, guess.depth)
    bounds = Bounds(
        t0=(t0 - 0.5 * guess.duration_days, t0 + 0.5 * guess.duration_days),
        period=(guess.period * 0.995, guess.period * 1.005),
    )
    start = initial_vector(guess)
    posterior = TransitPosterior(t, f, e, bounds, start)

    rng = np.random.default_rng(settings.seed)
    scales = np.array(
        [
            guess.duration_days * 0.01,
            guess.period * 1e-5,
            start[2] * 0.01,
            0.05,
            0.01,
            0.05,
            0.05,
            1e-5,
        ]
    )
    walkers = np.empty((settings.walkers, NDIM))
    for k in range(settings.walkers):
        for _ in range(1000):
            trial = start + scales * rng.standard_normal(NDIM)
            trial[3] = abs(trial[3])
            if math.isfinite(posterior(trial)):
                walkers[k] = trial
                break
        else:
            raise FitError("could not place walkers inside the priors")

    sampler = emcee.EnsembleSampler(settings.walkers, NDIM, posterior)
    sampler.random_state = np.random.RandomState(settings.seed).get_state()
    sampler.run_mcmc(walkers, settings.steps, progress=False)

    chain = sampler.get_chain(discard=settings.burn, flat=True)
    # tol=0: emcee neither raises nor logs; convergence is judged below with autocorr_factor.
    tau = sampler.get_autocorr_time(discard=settings.burn, tol=0)
    tau_max = float(np.max(tau)) if np.all(np.isfinite(tau)) else None
    n_post = settings.steps - settings.burn
    acceptance = sampler.acceptance_fraction
    convergence = Convergence(
        tau_max=tau_max,
        n_post_burn=n_post,
        autocorr_factor=settings.autocorr_factor,
        converged=tau_max is not None and n_post > settings.autocorr_factor * tau_max,
        acceptance_mean=float(np.mean(acceptance)),
        acceptance_min=float(np.min(acceptance)),
    )
    return FitResult(
        rp_rs=summarize(chain[:, 2]),
        impact_parameter=summarize(chain[:, 3]),
        a_rs=summarize(np.exp(chain[:, 4])),
        t0=summarize(chain[:, 0]),
        period=summarize(chain[:, 1]),
        rp_rs_samples=chain[:, 2],
        convergence=convergence,
        n_points=int(t.size),
    )


def planet_radius(rp_rs_samples: np.ndarray, stellar_radius: Measurement, seed: int) -> Measurement:
    """Rp in Earth radii; the stellar radius error (split normal) is propagated."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(rp_rs_samples.size)
    radius = stellar_radius.value + np.where(
        z >= 0, z * stellar_radius.err_upper, z * stellar_radius.err_lower
    )
    return summarize(rp_rs_samples * radius * RSUN_IN_REARTH)
