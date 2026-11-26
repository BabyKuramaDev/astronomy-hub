import numpy as np
import pytest

from contexts.modeling.domain.fit import (
    RSUN_IN_REARTH,
    ChainSettings,
    FitError,
    fit_transit,
    planet_radius,
    summarize,
)
from contexts.modeling.domain.transit import Guess, limb_darkening
from contexts.modeling.tests.conftest import DURATION_HOURS, TRUE, batman_lc
from shared.contracts import Measurement

SHORT = ChainSettings(walkers=16, steps=150, burn=50, seed=7, autocorr_factor=50.0)
GUESS = Guess(
    t0=TRUE["t0"] + 0.002,
    period=TRUE["period"] * 1.0001,
    duration_days=DURATION_HOURS / 24,
    depth=0.011,
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


def test_short_chain_recovers_radius_ratio() -> None:
    time, flux, err = batman_lc()
    result = fit_transit(time, flux, err, GUESS, SHORT, window_durations=3.0)
    assert result.rp_rs.value == pytest.approx(TRUE["rp"], rel=0.05)
    assert result.period.value == pytest.approx(TRUE["period"], rel=1e-4)
    assert result.convergence.n_post_burn == 100
    assert 0.0 < result.convergence.acceptance_mean < 1.0
    assert not result.convergence.converged  # 100 steps cannot be 50 autocorrelation times


def test_fit_is_deterministic_with_seed() -> None:
    time, flux, err = batman_lc()
    settings = ChainSettings(walkers=16, steps=40, burn=10, seed=7, autocorr_factor=50.0)
    a = fit_transit(time, flux, err, GUESS, settings, window_durations=3.0)
    b = fit_transit(time, flux, err, GUESS, settings, window_durations=3.0)
    assert a.rp_rs == b.rp_rs
    np.testing.assert_array_equal(a.rp_rs_samples, b.rp_rs_samples)


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        (ChainSettings(walkers=8, steps=40, burn=10, seed=1, autocorr_factor=50.0), "walkers"),
        (ChainSettings(walkers=16, steps=40, burn=40, seed=1, autocorr_factor=50.0), "burn"),
    ],
)
def test_invalid_chain_settings(settings: ChainSettings, message: str) -> None:
    time, flux, err = batman_lc()
    with pytest.raises(FitError, match=message):
        fit_transit(time, flux, err, GUESS, settings, window_durations=3.0)


def test_planet_radius_propagates_stellar_error() -> None:
    samples = np.full(100_000, 0.1)
    radius = planet_radius(samples, Measurement(value=1.0, err_lower=0.05, err_upper=0.1), seed=1)
    assert radius.value == pytest.approx(0.1 * RSUN_IN_REARTH, rel=0.01)
    assert radius.err_lower == pytest.approx(0.005 * RSUN_IN_REARTH, rel=0.03)
    assert radius.err_upper == pytest.approx(0.01 * RSUN_IN_REARTH, rel=0.03)


def test_solar_to_earth_radius_comes_from_astropy_constants() -> None:
    from astropy import constants

    assert (constants.R_sun / constants.R_earth).decompose().value == RSUN_IN_REARTH
