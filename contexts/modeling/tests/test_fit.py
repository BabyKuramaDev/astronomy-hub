import numpy as np
import pytest

from contexts.modeling.domain.fit import (
    RSUN_IN_REARTH,
    ChainSettings,
    FitError,
    FitSettings,
    fit_mcmc,
    fit_quick,
    planet_radius,
    summarize,
)
from contexts.modeling.domain.transit import Guess, limb_darkening, total_duration_days
from contexts.modeling.tests.conftest import DURATION_HOURS, TRUE, batman_lc
from shared.contracts import Measurement

SETTINGS = FitSettings(seed=7, window_durations=3.0, jitter_min=1e-9, jitter_max=0.05)
SHORT = ChainSettings(walkers=20, steps=150, burn=50, autocorr_factor=50.0)
GUESS = Guess(
    t0=TRUE["t0"] + 0.002,
    period=TRUE["period"] * 1.0001,
    duration_days=DURATION_HOURS / 24,
    depth=0.011,
)
TRUE_T14_HOURS = 24.0 * float(
    total_duration_days(
        np.array(TRUE["period"]), np.array(TRUE["rp"]), np.array(TRUE["b"]), np.array(TRUE["a"])
    )
)


def test_limb_darkening_mapping() -> None:
    assert limb_darkening(0.0, 0.5) == (0.0, 0.0)
    u1, u2 = limb_darkening(1.0, 0.5)
    assert (u1, u2) == pytest.approx((1.0, 0.0))


def test_summarize_percentiles() -> None:
    m = summarize(np.random.default_rng(0).normal(5.0, 2.0, 200_000))
    assert m.value == pytest.approx(5.0, abs=0.02)
    assert m.err_lower == pytest.approx(2.0, rel=0.02)
    assert m.err_upper == pytest.approx(2.0, rel=0.02)


def test_total_duration_of_a_central_transit() -> None:
    t14 = total_duration_days(np.array(10.0), np.array(0.0), np.array(0.0), np.array(10.0))
    assert float(t14) == pytest.approx(10.0 / np.pi * np.arcsin(0.1))
    assert np.isnan(total_duration_days(np.array(1.0), np.array(0.1), np.array(2.0), np.array(5.0)))


def test_quick_fit_recovers_parameters_with_errors() -> None:
    time, flux, err = batman_lc()
    result = fit_quick(time, flux, err, GUESS, SETTINGS, n_samples=5000)
    assert result.method == "quick"
    assert result.convergence is None
    assert result.rp_rs.value == pytest.approx(TRUE["rp"], rel=0.05)
    assert result.period.value == pytest.approx(TRUE["period"], rel=1e-4)
    assert result.duration_hours.value == pytest.approx(TRUE_T14_HOURS, rel=0.03)
    assert abs(result.rp_rs.value - TRUE["rp"]) < 4 * result.rp_rs.err_upper
    assert 0 < result.rp_rs.err_lower < 0.01


def test_quick_fit_measures_extra_white_noise() -> None:
    """Points have 400 ppm of noise but report 200 ppm: the jitter takes the rest."""
    time, flux, err = batman_lc(noise_ppm=400.0)
    result = fit_quick(time, flux, err / 2, GUESS, SETTINGS, n_samples=2000)
    assert result.jitter_ppm.value == pytest.approx(np.sqrt(400.0**2 - 200.0**2), rel=0.1)
    honest = fit_quick(time, flux, err, GUESS, SETTINGS, n_samples=2000)
    assert honest.jitter_ppm.value < 60.0


def test_quick_fit_is_deterministic() -> None:
    time, flux, err = batman_lc()
    a = fit_quick(time, flux, err, GUESS, SETTINGS, n_samples=1000)
    b = fit_quick(time, flux, err, GUESS, SETTINGS, n_samples=1000)
    assert a.rp_rs == b.rp_rs
    assert a.jitter_ppm == b.jitter_ppm


def test_short_chain_recovers_radius_ratio() -> None:
    time, flux, err = batman_lc()
    result = fit_mcmc(time, flux, err, GUESS, SETTINGS, SHORT)
    assert result.method == "mcmc"
    assert result.rp_rs.value == pytest.approx(TRUE["rp"], rel=0.05)
    assert result.period.value == pytest.approx(TRUE["period"], rel=1e-4)
    assert result.convergence is not None
    assert result.convergence.n_post_burn == 100
    assert 0.0 < result.convergence.acceptance_mean < 1.0
    assert not result.convergence.converged  # 100 steps cannot be 50 autocorrelation times


def test_mcmc_is_deterministic_with_seed() -> None:
    time, flux, err = batman_lc()
    chain = ChainSettings(walkers=20, steps=40, burn=10, autocorr_factor=50.0)
    a = fit_mcmc(time, flux, err, GUESS, SETTINGS, chain)
    b = fit_mcmc(time, flux, err, GUESS, SETTINGS, chain)
    assert a.rp_rs == b.rp_rs
    np.testing.assert_array_equal(a.rp_rs_samples, b.rp_rs_samples)


@pytest.mark.parametrize(
    ("chain", "message"),
    [
        (ChainSettings(walkers=8, steps=40, burn=10, autocorr_factor=50.0), "walkers"),
        (ChainSettings(walkers=20, steps=40, burn=40, autocorr_factor=50.0), "burn"),
    ],
)
def test_invalid_chain_settings(chain: ChainSettings, message: str) -> None:
    time, flux, err = batman_lc()
    with pytest.raises(FitError, match=message):
        fit_mcmc(time, flux, err, GUESS, SETTINGS, chain)


def test_too_few_points_near_transits() -> None:
    time, flux, err = batman_lc()
    keep = slice(0, 50)
    with pytest.raises(FitError, match="points near the transits"):
        fit_quick(time[keep], flux[keep], err[keep], GUESS, SETTINGS, n_samples=100)


def test_planet_radius_propagates_stellar_error() -> None:
    samples = np.full(100_000, 0.1)
    radius = planet_radius(samples, Measurement(value=1.0, err_lower=0.05, err_upper=0.1), seed=1)
    assert radius.value == pytest.approx(0.1 * RSUN_IN_REARTH, rel=0.01)
    assert radius.err_lower == pytest.approx(0.005 * RSUN_IN_REARTH, rel=0.03)
    assert radius.err_upper == pytest.approx(0.01 * RSUN_IN_REARTH, rel=0.03)


def test_solar_to_earth_radius_comes_from_astropy_constants() -> None:
    from astropy import constants

    assert (constants.R_sun / constants.R_earth).decompose().value == RSUN_IN_REARTH
