import numpy as np
import pytest

from contexts.detection.domain.fold import fold
from contexts.detection.tests.conftest import TRANSIT
from tests.support.synthetic import Transit, box_transit, light_curve

KW = {"window_durations": 1.5, "n_bins": 15}


def test_fold_measures_depth_and_scatter() -> None:
    time, flux, _ = light_curve(days=27.0, transit=TRANSIT, noise_ppm=500.0, seed=5)
    result = fold(
        time,
        flux,
        period_days=TRANSIT.period_days,
        epoch_btjd=TRANSIT.epoch_btjd,
        duration_hours=TRANSIT.duration_hours,
        **KW,
    )
    assert result.in_transit.value_ppm == pytest.approx(3000.0, rel=0.05)
    assert result.oot_scatter_ppm == pytest.approx(500.0, rel=0.1)
    assert result.n_transits_covered == 12
    centre = result.bins[len(result.bins) // 2]
    assert centre.phase_hours == pytest.approx(0.0, abs=1e-9)
    assert centre.depth_ppm == pytest.approx(3000.0, rel=0.1)
    assert abs(result.bins[0].depth_ppm) < 300.0
    _, sigma = result.odd_even_difference
    assert sigma is not None
    assert sigma < 3.0
    assert result.odd.n_transits + result.even.n_transits == 12


def test_odd_even_error_includes_transit_to_transit_scatter() -> None:
    """Depths that drift between sectors must not look like a significant odd/even split."""
    time, flux, _ = light_curve(days=27.0, transit=TRANSIT, noise_ppm=200.0, seed=7)
    rng = np.random.default_rng(0)
    epochs = np.rint((time - TRANSIT.epoch_btjd) / TRANSIT.period_days).astype(int)
    scale = 1.0 + rng.normal(0.0, 0.05, epochs.max() - epochs.min() + 1)[epochs - epochs.min()]
    flux = 1.0 - (1.0 - flux) * np.where(box_transit(time, TRANSIT) < 1.0, scale, 1.0)
    result = fold(
        time,
        flux,
        period_days=TRANSIT.period_days,
        epoch_btjd=TRANSIT.epoch_btjd,
        duration_hours=TRANSIT.duration_hours,
        **KW,
    )
    core_points = 0.5 * TRANSIT.duration_hours * 30  # 2-minute cadence, central half
    white = 200.0 / np.sqrt(result.odd.n_transits * core_points)
    assert result.odd.err_ppm > 2.5 * white


def test_fold_flags_odd_even_difference() -> None:
    period = 2.0 * TRANSIT.period_days  # an eclipsing binary at twice the period
    time, flux, _ = light_curve(days=27.0, noise_ppm=500.0, seed=6)
    flux = flux * box_transit(time, Transit(period, TRANSIT.epoch_btjd, 2.5, 5000.0))
    flux = flux * box_transit(
        time, Transit(period, TRANSIT.epoch_btjd + TRANSIT.period_days, 2.5, 2000.0)
    )
    result = fold(
        time,
        flux,
        period_days=TRANSIT.period_days,
        epoch_btjd=TRANSIT.epoch_btjd,
        duration_hours=2.5,
        **KW,
    )
    diff, sigma = result.odd_even_difference
    assert abs(diff) == pytest.approx(3000.0, rel=0.1)
    assert sigma > 10


def test_fold_without_transit_points() -> None:
    time = np.linspace(1000.0, 1000.3, 50)
    result = fold(time, np.ones(50), period_days=5.0, epoch_btjd=1003.0, duration_hours=2.0, **KW)
    assert result.in_transit.value_ppm is None
    assert result.n_transits_covered == 0
    assert result.odd_even_difference == (None, None)
