from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest

from contexts.detection.application.search_period import params_from
from contexts.detection.domain.bls import (
    Candidate,
    SearchError,
    bin_lightcurve,
    first_epoch,
    harmonic_ratio,
    max_duration_days,
    search_periods,
    triage,
)
from contexts.detection.tests.conftest import TRANSIT
from shared.mission import load_mission
from tests.support.synthetic import Transit, box_transit, light_curve

PARAMS = params_from(load_mission("exoplanets").detection)


def test_bin_lightcurve_averages() -> None:
    time = np.array([0.0, 1 / 1440, 2 / 1440, 20 / 1440])
    t, f, e = bin_lightcurve(time, np.array([1.0, 3.0, 5.0, 7.0]), np.full(4, 2.0), 10.0)
    np.testing.assert_allclose(f, [3.0, 7.0])
    np.testing.assert_allclose(e, [2.0 / np.sqrt(3), 2.0])
    assert t.size == 2


@pytest.mark.parametrize(
    ("period", "reference", "expected"),
    [
        (4.69, 2.345, Fraction(2)),
        (1.1725, 2.345, Fraction(1, 2)),
        (8.2075, 2.345, Fraction(7, 2)),
        (6.2533, 2.345, Fraction(8, 3)),
        (2.345 * 14, 2.345, Fraction(14)),
        (2.345 / 15, 2.345, Fraction(1, 15)),
        (2.345, 2.345, None),
        (3.3, 2.345, None),
    ],
)
def test_harmonic_ratio(period: float, reference: float, expected: Fraction | None) -> None:
    assert harmonic_ratio(period, reference, 12, 0.002) == expected


def test_first_epoch() -> None:
    assert first_epoch(1003.0, 1.0, 1000.2) == pytest.approx(1001.0)
    assert first_epoch(990.5, 2.0, 1000.0) == pytest.approx(1000.5)


def test_search_recovers_injected_period() -> None:
    time, flux, err = light_curve(days=27.0, transit=TRANSIT, noise_ppm=1000.0, seed=2)
    outcome = search_periods(time, flux, err, PARAMS)
    best = outcome.peaks[0]
    assert best.period_days == pytest.approx(TRANSIT.period_days, rel=1e-3)
    assert best.depth_ppm == pytest.approx(TRANSIT.depth_ppm, rel=0.2)
    assert best.snr > 30
    assert best.n_transits >= 10
    assert time.min() <= best.epoch_btjd < time.min() + best.period_days


def test_harmonics_are_annotated_not_kept() -> None:
    time, flux, err = light_curve(days=27.0, transit=TRANSIT, noise_ppm=1000.0, seed=2)
    outcome = search_periods(time, flux, err, PARAMS)
    harmonics = [d for d in outcome.discarded if d.reason == "harmonic"]
    assert harmonics
    assert all(d.harmonic_of == 0 for d in harmonics)
    assert Fraction(1, 2) in {d.ratio for d in harmonics}
    for d in harmonics:
        ratio = d.candidate.period_days / outcome.peaks[0].period_days
        assert ratio == pytest.approx(float(d.ratio), rel=0.002)


def test_second_planet_is_kept() -> None:
    time, flux, err = light_curve(days=54.0, transit=TRANSIT, noise_ppm=800.0, seed=3)
    flux = flux * box_transit(time, Transit(5.1234, 1001.3, 3.5, 2000.0))
    periods = [p.period_days for p in search_periods(time, flux, err, PARAMS).peaks]
    assert any(abs(p - 5.1234) / 5.1234 < 1e-3 for p in periods)


def candidate(period: float, depth: float = 1000.0, power: float = 10.0) -> Candidate:
    return Candidate(period, 1000.0, 2.0, depth, depth / 100.0, power)


def test_triage_discards_non_positive_depth_and_harmonics() -> None:
    ranked = [
        (candidate(2.0), 1000.0),
        (candidate(2.01), 1000.0),  # same peak as 2.0 (within peak_separation)
        (candidate(3.3, depth=0.0), 1000.0),
        (candidate(4.0), 1000.0),  # 2/1 harmonic of 2.0
        (candidate(5.5, depth=-20.0), 1000.0),
        (candidate(6.9), 1000.0),
    ]
    peaks, discarded = triage(ranked, PARAMS, lambda c, t: 7)
    assert [p.period_days for p in peaks] == [2.0, 6.9]
    assert all(p.n_transits == 7 for p in peaks)
    reasons = [(d.candidate.period_days, d.reason, d.harmonic_of, d.ratio) for d in discarded]
    assert reasons == [
        (3.3, "non_positive_depth", None, None),
        (4.0, "harmonic", 0, Fraction(2)),
        (5.5, "non_positive_depth", None, None),
    ]


def test_triage_stops_at_n_peaks() -> None:
    ranked = [(candidate(1.0 + 0.37 * k), 1000.0) for k in range(40)]
    peaks, _ = triage(ranked, replace(PARAMS, harmonic_max_integer=2), lambda c, t: 3)
    assert len(peaks) == PARAMS.n_peaks


def test_inverted_light_curve_keeps_only_positive_depths() -> None:
    time, flux, err = light_curve(days=27.0, transit=TRANSIT, noise_ppm=1000.0, seed=2)
    outcome = search_periods(time, 2.0 - flux, err, PARAMS)  # every dip becomes a bump
    assert all(p.depth_ppm > 0 for p in outcome.peaks)
    # The bumps themselves are never reported as a transit at their period. (Boxes between
    # bumps still reach a white-noise SNR above 8: see the M2 note on gate 3.)
    assert all(abs(p.period_days / TRANSIT.period_days - 1) > 0.01 for p in outcome.peaks)


def test_short_baseline_is_rejected() -> None:
    time, flux, err = light_curve(days=0.8, noise_ppm=1000.0, seed=1)
    with pytest.raises(SearchError, match="too short"):
        search_periods(time, flux, err, PARAMS)


def test_search_is_deterministic() -> None:
    time, flux, err = light_curve(days=27.0, transit=TRANSIT, noise_ppm=1000.0, seed=2)
    assert search_periods(time, flux, err, PARAMS) == search_periods(time, flux, err, PARAMS)


def test_max_duration_follows_keplers_third_law() -> None:
    # Sun-like density: a/R* = 215 at one year, so T_max ~ (P/pi) * asin(1/215) ~ 13 h.
    year = 365.25
    t_max = float(max_duration_days(year, 1.0, 0.0)) * 24.0
    assert t_max == pytest.approx(13.0, rel=0.03)
    short, long = max_duration_days(np.array([0.5, 10.0]), 0.05, 0.3)
    assert short == pytest.approx(0.25)  # the orbit is inside the star: half the period
    assert 0.25 < long < 10.0 / 2


def test_search_skips_impossible_durations() -> None:
    params = replace(PARAMS, stellar_density_min_solar=50.0, rp_rs_max=0.1)
    time, flux, err = light_curve(days=27.0, transit=TRANSIT, noise_ppm=1000.0, seed=2)
    outcome = search_periods(time, flux, err, params)
    for peak in outcome.peaks:
        limit = params.eccentricity_factor * float(max_duration_days(peak.period_days, 50.0, 0.1))
        assert peak.duration_hours <= limit * 24.0 + 1e-9


def test_the_mission_limit_rules_out_six_hours_at_short_periods() -> None:
    """With the fallback density and the eccentricity margin, a 6 h transit at P = 0.6 d
    (a/R* of about 1, an orbit grazing the star) is no longer searched; with the old 0.05
    it was allowed at every period."""
    from shared.mission import load_mission

    limit = load_mission("exoplanets").detection.duration_limit
    hours = (
        limit.eccentricity_factor
        * float(max_duration_days(0.598, limit.stellar_density_min_solar, limit.rp_rs_max))
        * 24.0
    )
    assert hours < 6.0
    assert float(max_duration_days(0.598, 0.05, limit.rp_rs_max)) * 24.0 > 6.0


def test_inverted_floor_and_sde() -> None:
    time, flux, err = light_curve(days=27.0, transit=TRANSIT, noise_ppm=1000.0, seed=2)
    outcome = search_periods(time, flux, err, PARAMS)
    assert 0.0 < outcome.inverted_snr_max < outcome.peaks[0].snr
    assert outcome.peaks[0].sde > 5.0
