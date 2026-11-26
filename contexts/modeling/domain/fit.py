"""Transit fits with a jitter term: quick (least squares) and mcmc (emcee).

quick: least squares on errors inflated by the jitter, which is re-estimated from
the residuals; parameter errors come from the covariance (Laplace approximation),
sampled with a fixed seed so derived quantities (a/R*, T14, Rp) get errors too.

mcmc: emcee over the same parameters plus log_jitter, with posterior percentiles
and a convergence report (autocorrelation time and acceptance fraction).
"""

import math
from dataclasses import dataclass

import emcee
import numpy as np
from astropy import constants
from scipy.optimize import least_squares

from contexts.modeling.domain.transit import (
    NDIM,
    Bounds,
    Guess,
    TransitPosterior,
    initial_vector,
    total_duration_days,
)
from shared.contracts import Measurement

RSUN_IN_REARTH = float((constants.R_sun / constants.R_earth).decompose().value)
# Index of each parameter in the vector (see transit.PARAMS).
T0, PERIOD, RP, B, LOG_A, Q1, Q2, F0, LOG_JITTER = range(NDIM)


class FitError(ValueError):
    """The fit cannot run with the given data or settings."""


@dataclass(frozen=True)
class FitSettings:
    seed: int
    window_durations: float
    jitter_min: float  # fractional flux
    jitter_max: float


@dataclass(frozen=True)
class ChainSettings:
    walkers: int
    steps: int
    burn: int
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
    method: str  # "quick" | "mcmc"
    rp_rs: Measurement
    impact_parameter: Measurement
    a_rs: Measurement
    t0: Measurement
    period: Measurement
    duration_hours: Measurement
    jitter_ppm: Measurement
    rp_rs_samples: np.ndarray
    convergence: Convergence | None
    n_points: int


def summarize(samples: np.ndarray) -> Measurement:
    finite = samples[np.isfinite(samples)]
    if finite.size == 0:
        raise FitError("no valid samples to summarize")
    p16, p50, p84 = np.percentile(finite, [16, 50, 84])
    return Measurement(
        value=float(p50), err_lower=float(max(p50 - p16, 0.0)), err_upper=float(max(p84 - p50, 0.0))
    )


def transit_window(time: np.ndarray, t0: float, period: float, half_width: float) -> np.ndarray:
    phase = (time - t0 + 0.5 * period) % period - 0.5 * period
    return np.abs(phase) <= half_width


@dataclass(frozen=True)
class _Problem:
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    guess: Guess
    bounds: Bounds
    start: np.ndarray
    posterior: TransitPosterior


def _prepare(
    time: np.ndarray, flux: np.ndarray, flux_err: np.ndarray, guess: Guess, settings: FitSettings
) -> _Problem:
    keep = transit_window(
        time, guess.t0, guess.period, settings.window_durations * guess.duration_days
    )
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
        log_jitter=(math.log(settings.jitter_min), math.log(settings.jitter_max)),
    )
    start = initial_vector(guess)
    start[LOG_JITTER] = 0.5 * (bounds.log_jitter[0] + bounds.log_jitter[1])
    return _Problem(t, f, e, guess, bounds, start, TransitPosterior(t, f, e, bounds, start))


def _derived(samples: np.ndarray) -> dict[str, Measurement]:
    a_rs = np.exp(samples[:, LOG_A])
    duration = total_duration_days(samples[:, PERIOD], samples[:, RP], samples[:, B], a_rs)
    return {
        "rp_rs": summarize(samples[:, RP]),
        "impact_parameter": summarize(samples[:, B]),
        "a_rs": summarize(a_rs),
        "t0": summarize(samples[:, T0]),
        "period": summarize(samples[:, PERIOD]),
        "duration_hours": summarize(duration * 24.0),
        "jitter_ppm": summarize(np.exp(samples[:, LOG_JITTER]) * 1e6),
    }


# Quick fit ----------------------------------------------------------------------------

# Bounds of the 8 transit parameters fitted by least squares (log_jitter is estimated
# apart). t0, period and f0 take theirs from the problem.
_LS_LOWER = np.array([-np.inf, -np.inf, 1e-4, 0.0, math.log(1.05), 0.0, 0.0, -np.inf])
_LS_UPPER = np.array([np.inf, np.inf, 0.99, 1.3, math.log(500.0), 1.0, 1.0, np.inf])
_JITTER_ITERATIONS = 3


def _jitter_estimate(resid: np.ndarray, err: np.ndarray, lo: float, hi: float) -> float:
    """Extra white noise that makes the residual variance match the reported errors."""
    excess = float(np.mean(resid**2) - np.mean(err**2))
    return float(np.clip(math.sqrt(excess) if excess > 0 else lo, lo, hi))


@dataclass(frozen=True)
class _Optimum:
    x: np.ndarray  # the 8 transit parameters
    jitter: float
    jac: np.ndarray


def _optimize(prob: _Problem, settings: FitSettings) -> _Optimum:
    """Least squares with the jitter re-estimated from the residuals between passes."""
    bd = prob.bounds
    lower, upper = _LS_LOWER.copy(), _LS_UPPER.copy()
    lower[[T0, PERIOD, F0]] = bd.t0[0], bd.period[0], bd.f0[0]
    upper[[T0, PERIOD, F0]] = bd.t0[1], bd.period[1], bd.f0[1]
    span = upper - lower
    pad = np.where(np.isfinite(span), 1e-6 * span, 0.0)
    x = np.clip(prob.start[: F0 + 1], lower + pad, upper - pad)
    jitter = settings.jitter_min
    fit = None
    for _ in range(_JITTER_ITERATIONS):
        sigma = np.sqrt(prob.flux_err**2 + jitter**2)
        log_jitter = math.log(jitter)

        def residuals(
            theta: np.ndarray, sigma: np.ndarray = sigma, log_jitter: float = log_jitter
        ) -> np.ndarray:
            return (prob.flux - prob.posterior.model(np.append(theta, log_jitter))) / sigma

        fit = least_squares(residuals, x, bounds=(lower, upper), x_scale="jac", method="trf")
        x = fit.x
        jitter = _jitter_estimate(
            fit.fun * sigma, prob.flux_err, settings.jitter_min, settings.jitter_max
        )
    assert fit is not None
    if not fit.success:
        raise FitError(f"least squares did not converge: {fit.message}")
    return _Optimum(x, jitter, fit.jac)


def fit_quick(
    time: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    guess: Guess,
    settings: FitSettings,
    n_samples: int,
) -> FitResult:
    prob = _prepare(time, flux, flux_err, guess, settings)
    opt = _optimize(prob, settings)
    x, jitter = opt.x, opt.jitter
    fit_jac = opt.jac

    # Covariance of the transit parameters, and of log(jitter) from its Fisher information.
    cov = np.linalg.pinv(fit_jac.T @ fit_jac)
    var = prob.flux_err**2 + jitter**2
    var_jitter2 = 2.0 / float(np.sum(1.0 / var**2))  # variance of jitter^2
    log_jitter_err = math.sqrt(var_jitter2) / (2.0 * jitter**2)
    full_cov = np.zeros((NDIM, NDIM))
    full_cov[: F0 + 1, : F0 + 1] = 0.5 * (cov + cov.T)
    full_cov[LOG_JITTER, LOG_JITTER] = log_jitter_err**2
    best = np.append(x, math.log(jitter))
    rng = np.random.default_rng(settings.seed)
    samples = rng.multivariate_normal(best, full_cov, size=n_samples, method="eigh")
    return FitResult(
        method="quick",
        rp_rs_samples=samples[:, RP],
        convergence=None,
        n_points=int(prob.time.size),
        **_derived(samples),
    )


# MCMC ---------------------------------------------------------------------------------


def fit_mcmc(
    time: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray,
    guess: Guess,
    settings: FitSettings,
    chain: ChainSettings,
) -> FitResult:
    if chain.walkers < 2 * NDIM:
        raise FitError(f"walkers must be at least {2 * NDIM} for {NDIM} parameters")
    if chain.burn >= chain.steps:
        raise FitError("burn must be below steps")
    prob = _prepare(time, flux, flux_err, guess, settings)
    # Walkers start around the least-squares optimum, which shortens the burn-in.
    opt = _optimize(prob, settings)
    start = np.append(opt.x, math.log(opt.jitter))
    posterior = prob.posterior

    rng = np.random.default_rng(settings.seed)
    scales = np.array(
        [
            prob.guess.duration_days * 0.01,
            prob.guess.period * 1e-5,
            start[RP] * 0.01,
            0.05,
            0.01,
            0.05,
            0.05,
            1e-5,
            0.5,
        ]
    )
    walkers = np.empty((chain.walkers, NDIM))
    for k in range(chain.walkers):
        for _ in range(1000):
            trial = start + scales * rng.standard_normal(NDIM)
            trial[B] = abs(trial[B])
            if math.isfinite(posterior(trial)):
                walkers[k] = trial
                break
        else:
            raise FitError("could not place walkers inside the priors")

    sampler = emcee.EnsembleSampler(chain.walkers, NDIM, posterior)
    sampler.random_state = np.random.RandomState(settings.seed).get_state()
    sampler.run_mcmc(walkers, chain.steps, progress=False)

    samples = sampler.get_chain(discard=chain.burn, flat=True)
    # tol=0: emcee neither raises nor logs; convergence is judged below with autocorr_factor.
    tau = sampler.get_autocorr_time(discard=chain.burn, tol=0)
    tau_max = float(np.max(tau)) if np.all(np.isfinite(tau)) else None
    n_post = chain.steps - chain.burn
    acceptance = sampler.acceptance_fraction
    convergence = Convergence(
        tau_max=tau_max,
        n_post_burn=n_post,
        autocorr_factor=chain.autocorr_factor,
        converged=tau_max is not None and n_post > chain.autocorr_factor * tau_max,
        acceptance_mean=float(np.mean(acceptance)),
        acceptance_min=float(np.min(acceptance)),
    )
    return FitResult(
        method="mcmc",
        rp_rs_samples=samples[:, RP],
        convergence=convergence,
        n_points=int(prob.time.size),
        **_derived(samples),
    )


def planet_radius(rp_rs_samples: np.ndarray, stellar_radius: Measurement, seed: int) -> Measurement:
    """Rp in Earth radii; the stellar radius error (split normal) is propagated."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(rp_rs_samples.size)
    radius = stellar_radius.value + np.where(
        z >= 0, z * stellar_radius.err_upper, z * stellar_radius.err_lower
    )
    return summarize(rp_rs_samples * radius * RSUN_IN_REARTH)
