"""The ten vetting gates, ported from open-exoplanet-hunt (MIT, with attribution).

Every gate is a pure function of the dossier inputs, the measurement parameters and
its thresholds from mission.yaml. A gate that cannot measure (too few transits, no
centroids, no stellar parameters) returns marginal with a note: it never fails for
lack of data. Deviations from the reference are noted where they happen.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from astropy import constants
from astropy.timeseries import BoxLeastSquares
from scipy.signal import medfilt

from contexts.vetting.domain.inputs import GateInputs, GateOutcome, MeasureParams
from contexts.vetting.domain.photometry import (
    Dip,
    per_transit_dips,
    signal_windows,
    sinusoid_amplitude,
    weighted_dip,
    windows,
)
from shared.contracts import Measurement
from shared.kernel.transits import odd_even, phase_days

RJUP_IN_REARTH = float((constants.R_jup / constants.R_earth).decompose().value)
RSUN_IN_REARTH = float((constants.R_sun / constants.R_earth).decompose().value)
G_SI = float(constants.G.to_value("m3 / (kg s2)"))
M_SUN_KG = float(constants.M_sun.to_value("kg"))
R_SUN_M = float(constants.R_sun.to_value("m"))
SECONDS_PER_DAY = 86400.0

# Part of the ported algorithms (not thresholds): periods tried by gate 10, as multiples
# of P, and the number of harmonics of its joint series.
RAW_MULTIPLES = (1.0 / 3.0, 0.5, 1.0, 2.0)
CLEAN_MULTIPLES = (0.2, 0.25, 1.0 / 3.0, 0.4, 0.5, 2.0 / 3.0, 1.0)
JOINT_HARMONICS = 4
# Centroid detrending (reference): running median of up to 101 cadences.
CENTROID_KERNEL_MAX = 101
CENTROID_MIN_POINTS = 55


def _r(value: float | None, digits: int = 3) -> float | None:
    return None if value is None or not math.isfinite(value) else round(float(value), digits)


def _weights(inputs: GateInputs) -> np.ndarray:
    return 1.0 / inputs.flux_err**2


def primary_dip(inputs: GateInputs, params: MeasureParams) -> Dip | None:
    win = signal_windows(inputs, params)
    return weighted_dip(inputs.flux, _weights(inputs), win.in_transit, win.baseline)


# 1 catalog (info) -----------------------------------------------------------------------


def gate_catalog(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    cat = inputs.catalog
    if cat is None:
        return GateOutcome(
            "marginal",
            None,
            None,
            "catalog.json is not in the dossier (in eval mode Catalog runs last); "
            "this gate never enters the verdict",
        )
    if cat.known_matches:
        return GateOutcome(
            "fail",
            float(len(cat.known_matches)),
            0.0,
            f"already catalogued at this period ({cat.status}): {', '.join(cat.known_matches)}",
        )
    return GateOutcome("pass", 0.0, 0.0, f"no catalog entry at this period ({cat.status})")


# 2 coverage ------------------------------------------------------------------------------


def gate_coverage(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    """Enough transits with data, in one sector or several. Whether the signal shows up in
    every sector, when there are several, is the coherence gate's job (gate 4)."""
    win = signal_windows(inputs, params)
    dips = per_transit_dips(inputs.flux, _weights(inputs), inputs.sector, win)
    sectors = sorted({d.sector for d in dips})
    ok = len(dips) >= cfg.min_transits
    note = f"{len(dips)} transits with data in sectors {sectors}; need at least {cfg.min_transits}"
    if ok and len(sectors) == 1:
        note += "; a single sector, so repetition across sectors is not tested"
    return GateOutcome(
        "pass" if ok else "fail",
        float(len(dips)),
        float(cfg.min_transits),
        note,
        {"n_transits": float(len(dips)), "n_sectors": float(len(sectors))},
    )


# 3 snr -----------------------------------------------------------------------------------


def gate_snr(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    threshold = max(inputs.snr_min, inputs.inverted_snr_max)
    above_min = inputs.snr >= inputs.snr_min
    above_floor = inputs.snr > inputs.inverted_snr_max
    if above_min and above_floor:
        note = "SNR above snr_min and above the noise floor of the inverted curve"
    elif not above_min:
        note = f"SNR below snr_min ({inputs.snr_min:g})"
    else:
        note = (
            f"SNR not above the noise floor: the inverted curve reaches "
            f"{inputs.inverted_snr_max:.1f}, so a dip this strong can be noise"
        )
    return GateOutcome(
        "pass" if above_min and above_floor else "fail",
        _r(inputs.snr, 2),
        _r(threshold, 2),
        note,
        {"snr_min": inputs.snr_min, "inverted_snr_max": _r(inputs.inverted_snr_max, 2)},
    )


# 4 holdout -------------------------------------------------------------------------------


def gate_holdout(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    """Train BLS on every sector but one, predict the held-out sector's transits.

    The reference calls it leave-one-epoch-out; with several sectors it holds out a whole
    sector. With a single sector it holds out one transit at a time (see _holdout_epochs).
    """
    duration = inputs.duration_hours / 24.0 * params.duration_scale
    weights = _weights(inputs)
    sectors = [int(s) for s in np.unique(inputs.sector)]
    grid = np.linspace(
        inputs.period_days * (1 - cfg.period_window),
        inputs.period_days * (1 + cfg.period_window),
        cfg.n_periods,
    )
    if len(sectors) < 2:
        return _holdout_epochs(inputs, params, cfg, duration, weights, grid)
    zs: dict[str, float | None] = {}
    for held in sectors:
        train = inputs.sector != held
        test = ~train
        bls = BoxLeastSquares(inputs.time[train], inputs.flux[train], dy=inputs.flux_err[train])
        result = bls.power(grid, duration, objective="snr")
        best = int(np.nanargmax(result.power))
        win = windows(
            inputs.time[test],
            float(result.period[best]),
            float(result.transit_time[best]),
            duration,
            params,
        )
        dip = (
            weighted_dip(inputs.flux[test], weights[test], win.in_transit, win.baseline)
            if win.in_transit.sum() >= 2 and win.baseline.sum() >= 4
            else None
        )
        zs[f"z_sector_{held}"] = _r(dip.snr, 2) if dip else None
    measured = [z for z in zs.values() if z is not None]
    if len(measured) < 2:
        return GateOutcome(
            "marginal", None, cfg.min_z, "fewer than two sectors cover a predicted transit", zs
        )
    z_min, z_mean = min(measured), float(np.mean(measured))
    ok = z_min >= cfg.min_z and z_mean >= cfg.min_mean_z
    return GateOutcome(
        "pass" if ok else "fail",
        _r(z_min, 2),
        cfg.min_z,
        f"held-out sectors: minimum Z {z_min:.1f} (need {cfg.min_z:g}), "
        f"mean Z {z_mean:.1f} (need {cfg.min_mean_z:g})",
        {**zs, "z_mean": _r(z_mean, 2)},
    )


def _holdout_epochs(
    inputs: GateInputs,
    params: MeasureParams,
    cfg: Any,
    duration: float,
    weights: np.ndarray,
    grid: np.ndarray,
) -> GateOutcome:
    """Single sector: hold out each transit in turn, train BLS on the others, and measure the
    depth at the predicted time of the held-out one. A lone transit of a small planet does
    not clear a threshold, so the held-out depths are combined into one statistic (their
    inverse-variance mean over its standard error) and the threshold applies to that."""
    win = signal_windows(inputs, params)
    epochs = [int(e) for e in np.unique(win.epochs[win.in_transit])]
    if len(epochs) < cfg.min_epochs:
        return GateOutcome(
            "marginal",
            None,
            cfg.min_mean_z,
            f"a single sector with {len(epochs)} transits: fewer than "
            f"{cfg.min_epochs}, nothing to train on",
        )
    dips = []
    for held in epochs:
        test = win.epochs == held
        train = ~test
        bls = BoxLeastSquares(inputs.time[train], inputs.flux[train], dy=inputs.flux_err[train])
        result = bls.power(grid, duration, objective="snr")
        best = int(np.nanargmax(result.power))
        pred = windows(
            inputs.time[test],
            float(result.period[best]),
            float(result.transit_time[best]),
            duration,
            params,
        )
        if pred.in_transit.sum() >= 1 and pred.baseline.sum() >= 2:
            dip = weighted_dip(inputs.flux[test], weights[test], pred.in_transit, pred.baseline)
            if dip is not None and dip.err_ppm > 0:
                dips.append(dip)
    if len(dips) < cfg.min_epochs:
        return GateOutcome(
            "marginal",
            None,
            cfg.min_mean_z,
            f"only {len(dips)} held-out transits have data at the predicted "
            f"time (need {cfg.min_epochs})",
        )
    w = np.array([1.0 / d.err_ppm**2 for d in dips])
    depth = np.array([d.ppm for d in dips])
    mean = float(np.sum(w * depth) / np.sum(w))
    z = mean * math.sqrt(float(np.sum(w)))
    ok = z >= cfg.min_mean_z
    return GateOutcome(
        "pass" if ok else "fail",
        _r(z, 2),
        cfg.min_mean_z,
        f"a single sector: {len(dips)} transits held out one at a time; combined depth "
        f"{mean:.0f} ppm, Z {z:.1f} (need {cfg.min_mean_z:g})",
        {"n_held_out": float(len(dips)), "z_combined": _r(z, 2), "depth_ppm": _r(mean, 1)},
    )


# 5 odd-even ------------------------------------------------------------------------------


def gate_odd_even(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    """Same criterion as detection's fold: per-transit depths, each group's own scatter."""
    duration = inputs.duration_hours / 24.0 * params.duration_scale
    phase = phase_days(inputs.time, inputs.period_days, inputs.epoch_btjd)
    out = np.abs(phase) > duration
    baseline = float(np.median(inputs.flux[out])) if out.any() else 1.0
    core = np.abs(phase) < 0.25 * duration
    epochs = np.rint((inputs.time - inputs.epoch_btjd) / inputs.period_days).astype(np.int64)
    split = odd_even(inputs.flux, epochs, core, baseline, min_points=3)
    metrics = {
        "odd_ppm": _r(split.odd.value_ppm, 1),
        "even_ppm": _r(split.even.value_ppm, 1),
        "n_odd": float(split.odd.n_transits),
        "n_even": float(split.even.n_transits),
    }
    if split.difference_sigma is None:
        return GateOutcome(
            "marginal",
            None,
            cfg.max_sigma,
            "fewer than two odd or two even transits to compare",
            metrics,
        )
    sigma = split.difference_sigma
    return GateOutcome(
        "fail" if sigma >= cfg.max_sigma else "pass",
        _r(sigma, 2),
        cfg.max_sigma,
        f"odd {split.odd.value_ppm:.0f} ppm vs even {split.even.value_ppm:.0f} ppm: "
        f"{sigma:.1f} sigma apart",
        metrics,
    )


# 6 secondary -----------------------------------------------------------------------------


def _event_depth(dips: list[Any]) -> Dip | None:
    """Mean of per-event dips; the error is the larger of their scatter and the white error."""
    if len(dips) < 2:
        return None
    values = np.array([d.dip.ppm for d in dips])
    white = np.array([d.dip.err_ppm for d in dips])
    scatter = float(values.std(ddof=1) / math.sqrt(values.size))
    white_err = float(1.0 / math.sqrt(np.sum(1.0 / white**2)))
    return Dip(float(values.mean()), max(scatter, white_err))


def gate_secondary(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    """Eclipse at phase 0.5, against a local baseline around it.

    Passes when not significant, or when significant but shallower than
    max_depth_ratio of the primary (an occultation compatible with a planet). The
    reference code only checks the significance; its docstring adds the 30% clause.
    """
    weights = _weights(inputs)
    primary = _event_depth(
        per_transit_dips(inputs.flux, weights, inputs.sector, signal_windows(inputs, params))
    )
    secondary = _event_depth(
        per_transit_dips(
            inputs.flux, weights, inputs.sector, signal_windows(inputs, params, shift=0.5)
        )
    )
    if primary is None or secondary is None or primary.ppm <= 0:
        return GateOutcome(
            "marginal", None, cfg.min_sigma, "fewer than two primary or secondary events"
        )
    sigma = secondary.snr
    ratio = secondary.ppm / primary.ppm
    metrics = {
        "secondary_ppm": _r(secondary.ppm, 1),
        "secondary_err_ppm": _r(secondary.err_ppm, 1),
        "primary_ppm": _r(primary.ppm, 1),
        "depth_ratio": _r(ratio, 4),
        "max_depth_ratio": cfg.max_depth_ratio,
    }
    if sigma < cfg.min_sigma:
        status, note = "pass", f"no significant secondary eclipse ({sigma:.1f} sigma)"
    elif ratio < cfg.max_depth_ratio:
        status = "pass"
        note = (
            f"significant secondary eclipse ({sigma:.1f} sigma) of {secondary.ppm:.0f} ppm, "
            f"{100 * ratio:.1f}% of the primary: an occultation compatible with a planet"
        )
    else:
        status = "fail"
        note = (
            f"significant secondary eclipse ({sigma:.1f} sigma) of {secondary.ppm:.0f} ppm, "
            f"{100 * ratio:.0f}% of the primary: too deep for a planet"
        )
    return GateOutcome(status, _r(sigma, 2), cfg.min_sigma, note, metrics)


# 7 plausibility --------------------------------------------------------------------------


def circular_duration_days(period_days: float, radius_rsun: float, mass_msun: float) -> float:
    """Central (b = 0) duration of a circular orbit, as in the reference (R*/a capped at 0.95)."""
    p_s = period_days * SECONDS_PER_DAY
    a_m = (G_SI * mass_msun * M_SUN_KG * p_s**2 / (4.0 * math.pi**2)) ** (1.0 / 3.0)
    return period_days / math.pi * math.asin(min(0.95, radius_rsun * R_SUN_M / a_m))


def _planet_radius(inputs: GateInputs) -> tuple[Measurement | None, str]:
    """From model.json; without a fitted model, sqrt(depth) times the stellar radius."""
    star = inputs.stellar_radius
    model = inputs.model if inputs.model is not None and inputs.model.failure is None else None
    if model is not None and model.planet_radius_rearth is not None:
        return model.planet_radius_rearth, f"model.json ({model.method})"
    if model is None and star is not None and inputs.depth_ppm > 0:
        rp = math.sqrt(inputs.depth_ppm * 1e-6) * RSUN_IN_REARTH
        return (
            Measurement(
                value=rp * star.value, err_lower=rp * star.err_lower, err_upper=rp * star.err_upper
            ),
            "signal.json depth and star.json radius (no fitted model.json)",
        )
    return None, "no stellar radius in the TIC"


@dataclass(frozen=True)
class _Check:
    status: str
    note: str


def gate_plausibility(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    checks: list[_Check] = []
    metrics: dict[str, float | None] = {}
    max_rearth = cfg.planet_radius_max_rjup * RJUP_IN_REARTH
    marginal_rearth = cfg.planet_radius_marginal_rjup * RJUP_IN_REARTH
    radius, source = _planet_radius(inputs)
    if radius is not None:
        metrics |= {
            "radius_rearth": _r(radius.value, 2),
            "radius_lower_rearth": _r(radius.lower, 2),
            "radius_upper_rearth": _r(radius.upper, 2),
            "radius_max_rearth": _r(max_rearth, 2),
            "radius_marginal_rearth": _r(marginal_rearth, 2),
        }
        if radius.lower > max_rearth:
            checks.append(_Check("fail", f"radius {radius.value:.1f} R_earth is too large"))
        elif radius.upper < cfg.planet_radius_min_rearth:
            checks.append(_Check("fail", f"radius {radius.value:.2f} R_earth is too small"))
        elif radius.upper > max_rearth:
            checks.append(_Check("marginal", f"radius interval crosses {max_rearth:.1f} R_earth"))
        elif radius.value > marginal_rearth:
            checks.append(
                _Check(
                    "marginal",
                    f"radius {radius.value:.1f} R_earth is bigger than 99% of the known planets "
                    f"({marginal_rearth:.1f} R_earth)",
                )
            )
        else:
            checks.append(_Check("pass", f"radius {radius.value:.1f} R_earth from {source}"))

    star_r, star_m = inputs.stellar_radius, inputs.stellar_mass
    fitted = inputs.model if inputs.model is not None and inputs.model.failure is None else None
    if inputs.model is not None and inputs.model.failure is not None:
        # A failed fit is not evidence against a planet on its own: marginal, never fail.
        checks.append(_Check("marginal", f"model.json is a failed fit ({inputs.model.failure})"))
    duration_h = (
        fitted.duration_hours.value
        if fitted is not None and fitted.duration_hours is not None
        else inputs.duration_hours
    )
    if star_r is not None and star_m is not None:
        expected_h = circular_duration_days(inputs.period_days, star_r.value, star_m.value) * 24
        ratio = duration_h / expected_h
        lo, hi = cfg.duration_ratio
        metrics |= {"duration_hours": _r(duration_h, 3), "duration_ratio": _r(ratio, 3)}
        checks.append(
            _Check(
                "pass" if lo <= ratio <= hi else "fail",
                f"duration {duration_h:.2f} h is {ratio:.2f} of the circular b=0 duration "
                f"(allowed {lo:g}-{hi:g})",
            )
        )
    if not checks:
        return GateOutcome(
            "marginal", None, None, "no stellar radius or mass in the TIC: nothing to check"
        )
    if radius is None:
        checks.append(_Check("pass", "no stellar radius in the TIC: decided by the duration only"))
    status = next((s for s in ("fail", "marginal") if any(c.status == s for c in checks)), "pass")
    return GateOutcome(
        status,
        metrics.get("radius_rearth"),
        _r(max_rearth, 2),
        "; ".join(c.note for c in checks),
        metrics,
    )


# 8 centroid ------------------------------------------------------------------------------


def _detrended_centroid(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out = np.full(values.size, np.nan)
    n = int(valid.sum())
    if n <= CENTROID_MIN_POINTS:
        return out
    kernel = max(5, min(CENTROID_KERNEL_MAX, (n // 3) | 1))
    out[valid] = values[valid] - medfilt(values[valid], kernel_size=kernel)
    return out


def gate_centroid(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    duration = inputs.duration_hours / 24.0 * params.duration_scale
    dx_in, dx_out, dy_in, dy_out = [], [], [], []
    for sector in inputs.raw:
        valid = np.isfinite(sector.centroid_col) & np.isfinite(sector.centroid_row)
        dx = _detrended_centroid(sector.centroid_col, valid)
        dy = _detrended_centroid(sector.centroid_row, valid)
        win = windows(sector.time, inputs.period_days, inputs.epoch_btjd, duration, params)
        ok = np.isfinite(dx) & np.isfinite(dy)
        dx_in.append(dx[win.in_transit & ok])
        dy_in.append(dy[win.in_transit & ok])
        dx_out.append(dx[win.baseline & ok])
        dy_out.append(dy[win.baseline & ok])
    xi, xo = np.concatenate(dx_in or [[]]), np.concatenate(dx_out or [[]])
    yi, yo = np.concatenate(dy_in or [[]]), np.concatenate(dy_out or [[]])
    if xi.size < 5 or xo.size < 20:
        return GateOutcome(
            "marginal",
            None,
            cfg.max_sigma,
            "not enough centroid measurements in and out of transit",
        )
    mx, my = float(xi.mean() - xo.mean()), float(yi.mean() - yo.mean())
    sx = max(float(xo.std() / math.sqrt(xi.size)), 1e-9)
    sy = max(float(yo.std() / math.sqrt(yi.size)), 1e-9)
    shift_pix = math.hypot(mx, my)
    shift_arcsec = shift_pix * cfg.pixel_scale_arcsec
    sigma = math.hypot(mx / sx, my / sy)
    ok = sigma < cfg.max_sigma and shift_arcsec < cfg.max_shift_arcsec
    return GateOutcome(
        "pass" if ok else "fail",
        _r(sigma, 2),
        cfg.max_sigma,
        f"in-transit centroid shift of {shift_arcsec:.3f} arcsec ({sigma:.1f} sigma); "
        f"limits {cfg.max_sigma:g} sigma and {cfg.max_shift_arcsec:g} arcsec",
        {"shift_arcsec": _r(shift_arcsec, 4), "shift_mpix": _r(shift_pix * 1e3, 3)},
    )


# 9 coherence -----------------------------------------------------------------------------


def gate_coherence(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    weights = _weights(inputs)
    win = signal_windows(inputs, params)
    dips = per_transit_dips(inputs.flux, weights, inputs.sector, win)
    total = weighted_dip(inputs.flux, weights, win.in_transit, win.baseline)
    if len(dips) < 3 or total is None:
        return GateOutcome(
            "marginal", None, cfg.min_positive_fraction, "fewer than three transits measured"
        )
    positive = sum(d.dip.ppm > 0 for d in dips) / len(dips)
    strongest = max(dips, key=lambda d: d.dip.snr).epoch
    keep = win.epochs != strongest
    jack = weighted_dip(inputs.flux, weights, win.in_transit & keep, win.baseline & keep)
    jack_snr = jack.snr if jack else 0.0
    median = float(np.median([d.dip.ppm for d in dips]))
    ok = (
        positive >= cfg.min_positive_fraction
        and jack_snr >= cfg.min_jackknife_snr
        and median >= cfg.min_median_fraction * total.ppm
    )
    return GateOutcome(
        "pass" if ok else "fail",
        _r(positive, 3),
        cfg.min_positive_fraction,
        f"{positive:.0%} of {len(dips)} transits are dips; SNR without the strongest "
        f"{jack_snr:.1f} (need {cfg.min_jackknife_snr:g}); median transit "
        f"{median:.0f} ppm vs {total.ppm:.0f} ppm overall (need {cfg.min_median_fraction:g}x)",
        {
            "n_transits": float(len(dips)),
            "jackknife_snr": _r(jack_snr, 2),
            "median_ppm": _r(median, 1),
            "depth_ppm": _r(total.ppm, 1),
        },
    )


# 10 rotation -----------------------------------------------------------------------------


def gate_rotation(inputs: GateInputs, params: MeasureParams, cfg: Any) -> GateOutcome:
    """Sinusoids at P, its fractions and a 4-harmonic series, out of transit."""
    total = primary_dip(inputs, params)
    if total is None or total.ppm <= 0:
        return GateOutcome("marginal", None, cfg.max_clean_ratio, "no positive transit depth")
    duration = inputs.duration_hours / 24.0 * params.duration_scale
    period = inputs.period_days

    phase = phase_days(inputs.time, period, inputs.epoch_btjd)
    oot = np.abs(phase) > cfg.oot_durations * duration
    t, f = inputs.time[oot], inputs.flux[oot] - 1.0
    clean_amp = max(sinusoid_amplitude(t, f, period * m) for m in CLEAN_MULTIPLES)
    if t.size >= 20:
        cols = [np.ones(t.size)]
        for k in range(1, JOINT_HARMONICS + 1):
            omega = 2.0 * math.pi * k / period
            cols += [np.sin(omega * t), np.cos(omega * t)]
        beta, *_ = np.linalg.lstsq(np.column_stack(cols), f, rcond=None)
        lo = cfg.oot_durations * duration / period
        grid_phase = np.linspace(lo, 1.0 - lo, 400)
        grid_t = inputs.epoch_btjd + grid_phase * period
        curve = np.zeros_like(grid_t)
        for k in range(1, JOINT_HARMONICS + 1):
            omega = 2.0 * math.pi * k / period
            curve += beta[2 * k - 1] * np.sin(omega * grid_t) + beta[2 * k] * np.cos(omega * grid_t)
        clean_amp = max(clean_amp, 0.5 * float(curve.max() - curve.min()))

    raw_amp = 0.0
    if inputs.raw:
        rt = np.concatenate([s.time for s in inputs.raw])
        rf = np.concatenate([s.flux for s in inputs.raw])
        r_oot = np.abs(phase_days(rt, period, inputs.epoch_btjd)) > cfg.oot_durations * duration
        rt, rf = rt[r_oot], rf[r_oot] - np.median(rf[r_oot])
        if rt.size >= 20:
            raw_amp = max(sinusoid_amplitude(rt, rf, period * m) for m in RAW_MULTIPLES)

    clean_ratio = clean_amp * 1e6 / total.ppm
    raw_ratio = raw_amp * 1e6 / total.ppm
    ok = clean_ratio < cfg.max_clean_ratio and raw_ratio < cfg.max_raw_ratio
    return GateOutcome(
        "pass" if ok else "fail",
        _r(clean_ratio, 3),
        cfg.max_clean_ratio,
        f"out-of-transit sinusoid of {clean_amp * 1e6:.0f} ppm in the clean curve "
        f"({clean_ratio:.2f} of the depth, limit {cfg.max_clean_ratio:g}) and "
        f"{raw_amp * 1e6:.0f} ppm in the raw one ({raw_ratio:.2f}, limit {cfg.max_raw_ratio:g})",
        {
            "clean_amplitude_ppm": _r(clean_amp * 1e6, 1),
            "raw_amplitude_ppm": _r(raw_amp * 1e6, 1),
            "raw_ratio": _r(raw_ratio, 3),
            "depth_ppm": _r(total.ppm, 1),
        },
    )


# Registry --------------------------------------------------------------------------------

GateFn = Callable[[GateInputs, MeasureParams, Any], GateOutcome]


@dataclass(frozen=True)
class GateSpec:
    id: str
    fn: GateFn
    rerunnable: bool  # measures photometry, so run-gate may change its parameters


GATES: tuple[GateSpec, ...] = (
    GateSpec("catalog", gate_catalog, False),
    GateSpec("coverage", gate_coverage, False),
    GateSpec("snr", gate_snr, False),
    GateSpec("holdout", gate_holdout, True),
    GateSpec("odd-even", gate_odd_even, True),
    GateSpec("secondary", gate_secondary, True),
    GateSpec("plausibility", gate_plausibility, False),
    GateSpec("centroid", gate_centroid, True),
    GateSpec("coherence", gate_coherence, True),
    GateSpec("rotation", gate_rotation, True),
)
GATE_IDS = tuple(g.id for g in GATES)


def gate_spec(gate_id: str) -> GateSpec | None:
    return next((g for g in GATES if g.id == gate_id), None)
