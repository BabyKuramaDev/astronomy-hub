import numpy as np
import pytest

from shared.kernel.transits import epoch_index, odd_even, phase_days, transit_depths


def _alternating(depth_odd: float, depth_even: float, jitter_ppm: float, n: int = 12):
    """Flat in-transit samples, one block of 20 per transit, with transit-to-transit jitter."""
    rng = np.random.default_rng(3)
    epochs = np.repeat(np.arange(n), 20)
    depth = np.where(epochs % 2 == 1, depth_odd, depth_even) + rng.normal(0, jitter_ppm, n)[epochs]
    flux = 1.0 - depth * 1e-6
    return flux, epochs


def test_phase_and_epoch() -> None:
    time = np.array([9.9, 10.0, 12.4, 13.1])
    np.testing.assert_allclose(phase_days(time, 2.0, 10.0), [-0.1, 0.0, 0.4, -0.9])
    np.testing.assert_array_equal(epoch_index(time, 2.0, 10.0), [0, 0, 1, 2])


def test_transit_depths_error_is_scatter_between_transits() -> None:
    flux, epochs = _alternating(1000.0, 1000.0, jitter_ppm=100.0)
    result = transit_depths(flux, epochs, 1.0, 3)
    assert result.n_transits == 12
    assert result.value_ppm == pytest.approx(1000.0, abs=100.0)
    assert result.err_ppm == pytest.approx(np.std(result.per_transit_ppm, ddof=1) / np.sqrt(12))


def test_odd_even_errors_come_from_each_group() -> None:
    """An eclipsing binary with alternating depths stays significant.

    Pooling both groups to estimate the scatter would give an error of about
    1500 / sqrt(6) ppm per group and only ~3 sigma; within each group it is ~50 ppm.
    """
    flux, epochs = _alternating(5000.0, 2000.0, jitter_ppm=50.0)
    result = odd_even(flux, epochs, np.ones(flux.size, bool), 1.0, 3)
    assert result.difference_ppm == pytest.approx(3000.0, rel=0.05)
    assert result.difference_sigma > 50
    pooled = np.std(np.r_[result.odd.per_transit_ppm, result.even.per_transit_ppm], ddof=1)
    assert 3000.0 / (pooled * np.sqrt(2 / 6)) < 4


def test_odd_even_needs_two_transits_per_group() -> None:
    flux, epochs = _alternating(1000.0, 1000.0, jitter_ppm=10.0, n=3)
    result = odd_even(flux, epochs, np.ones(flux.size, bool), 1.0, 3)
    assert result.odd.n_transits == 1
    assert result.difference_sigma is None
