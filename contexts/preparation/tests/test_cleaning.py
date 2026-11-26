import numpy as np
import pytest

from contexts.preparation.domain.cleaning import (
    SectorSeries,
    clean_sectors,
    normalize,
    robust_std,
    upper_outliers,
)
from tests.support.synthetic import Transit, light_curve

TRANSIT = Transit(period_days=1.7, epoch_btjd=1000.6, duration_hours=2.5, depth_ppm=4000.0)


def series(sector: int, start: float, **kwargs: object) -> SectorSeries:
    time, flux, err = light_curve(start=start, days=6.0, **kwargs)  # type: ignore[arg-type]
    return SectorSeries(sector, time, flux * 30000.0, err * 30000.0)


def test_normalize_divides_by_median() -> None:
    s = normalize(SectorSeries(1, np.arange(3.0), np.array([2.0, 4.0, 6.0]), np.ones(3)))
    np.testing.assert_allclose(s.flux, [0.5, 1.0, 1.5])
    np.testing.assert_allclose(s.flux_err, [0.25] * 3)


def test_normalize_rejects_non_positive_median() -> None:
    with pytest.raises(ValueError, match="positive"):
        normalize(SectorSeries(1, np.arange(3.0), np.zeros(3), np.ones(3)))


def test_upper_outliers_never_flags_dips() -> None:
    flux = np.ones(100)
    flux[10] = 1.5
    flux[20] = 0.5
    mask = upper_outliers(flux + np.random.default_rng(0).normal(0, 1e-3, 100), 4.0)
    assert mask[10]
    assert not mask[20]


def test_clean_removes_trend_and_keeps_transit_depth() -> None:
    raw = series(2, 1000.0, transit=TRANSIT, trend_amplitude=0.01, noise_ppm=200.0, seed=3)
    result = clean_sectors([raw], window_days=0.75, break_tolerance_days=0.5, sigma_upper=4.0)
    out_of_transit = result.flux[
        np.abs(((result.time_btjd - TRANSIT.epoch_btjd + 0.85) % 1.7) - 0.85) > 0.15
    ]
    assert robust_std(out_of_transit) < 300e-6
    assert abs(np.median(out_of_transit) - 1.0) < 1e-4
    assert 1.0 - result.flux.min() > 0.8 * TRANSIT.depth_ppm * 1e-6


def test_clean_stitches_sorted_with_sector_labels() -> None:
    a = series(3, 1030.0, seed=1)
    b = series(2, 1000.0, seed=2)
    result = clean_sectors([a, b], window_days=0.75, break_tolerance_days=0.5, sigma_upper=4.0)
    assert np.all(np.diff(result.time_btjd) >= 0)
    assert set(result.sector.tolist()) == {2, 3}
    assert [s.sector for s in result.stats] == [2, 3]
    assert result.sector.dtype == np.int16


def test_clean_clips_a_flare() -> None:
    raw = series(2, 1000.0, seed=4)
    flux = raw.flux.copy()
    flux[500:503] *= 1.05
    result = clean_sectors(
        [SectorSeries(2, raw.time_btjd, flux, raw.flux_err)],
        window_days=0.75,
        break_tolerance_days=0.5,
        sigma_upper=4.0,
    )
    assert result.stats[0].n_clipped >= 3
    assert result.flux.max() < 1.01


def test_clean_is_deterministic() -> None:
    raw = series(2, 1000.0, transit=TRANSIT, seed=5)
    kwargs = {"window_days": 0.75, "break_tolerance_days": 0.5, "sigma_upper": 4.0}
    a = clean_sectors([raw], **kwargs)
    b = clean_sectors([raw], **kwargs)
    np.testing.assert_array_equal(a.flux, b.flux)
