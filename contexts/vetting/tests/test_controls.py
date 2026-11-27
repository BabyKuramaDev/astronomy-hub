"""Synthetic controls: injected transits pass, impostors are rejected.

Ported from open-exoplanet-hunt (MIT): "break your tests on purpose; if a check never
fails you do not know whether it works."
"""

from dataclasses import replace

import numpy as np
import pytest

from contexts.vetting.domain.gates import GATES, RJUP_IN_REARTH, gate_spec
from contexts.vetting.domain.inputs import GateInputs, ModelInfo
from contexts.vetting.domain.verdict import GateStatus, verdict
from contexts.vetting.tests.synthetic import CONFIG, PARAMS, PERIOD, T0, make_inputs, with_flux
from shared.contracts import Measurement


def run(inputs: GateInputs) -> dict[str, str]:
    out = {}
    for spec in GATES:
        cfg = getattr(CONFIG.gates, spec.id.replace("-", "_"))
        out[spec.id] = spec.fn(inputs, PARAMS, cfg).status
    return out


def vetting_verdict(statuses: dict[str, str]) -> str:
    return verdict(
        [
            GateStatus(g, s, getattr(CONFIG.gates, g.replace("-", "_")).severity)
            for g, s in statuses.items()
        ]
    )


def test_positive_control_passes_every_gate() -> None:
    statuses = run(make_inputs())
    assert statuses.pop("catalog") == "not_evaluable"  # no catalog.json: info only
    assert set(statuses.values()) == {"pass"}, statuses
    assert vetting_verdict(run(make_inputs())) == "candidate"


@pytest.mark.parametrize(
    ("kwargs", "gate", "expected_verdict"),
    [
        ({"odd_depth": 950e-6, "even_depth": 200e-6}, "odd-even", "false_positive"),
        ({"drop_last_sector_signal": True}, "holdout", "inconclusive"),
        (
            {"odd_depth": 450e-6, "even_depth": 450e-6, "sin_mod_amp": 400e-6},
            "rotation",
            "inconclusive",
        ),
    ],
)
def test_negative_controls(kwargs: dict, gate: str, expected_verdict: str) -> None:
    statuses = run(make_inputs(**kwargs))
    assert statuses[gate] == "fail", statuses
    assert vetting_verdict(statuses) == expected_verdict


def test_small_significant_occultation_passes_with_a_note() -> None:
    """A significant secondary below the deepest possible occultation passes, with a note:
    a close-in giant (Rp/R* 0.1, a/R* 3) could show over 1000 ppm, so 60 ppm is within it."""

    def m(v: float) -> Measurement:
        return Measurement(value=v, err_lower=0.01 * v, err_upper=0.01 * v)

    giant = ModelInfo(
        rp_rs=m(0.1), planet_radius_rearth=None, duration_hours=m(1.7), method="quick", a_rs=m(3.0)
    )
    inputs = replace(make_inputs(odd_depth=600e-6, even_depth=600e-6, sec_depth=60e-6), model=giant)
    cfg = CONFIG.gates.secondary
    outcome = gate_spec("secondary").fn(inputs, PARAMS, cfg)  # type: ignore[union-attr]
    assert outcome.value is not None
    assert outcome.value >= cfg.min_sigma
    assert outcome.status == "pass"
    assert "compatible with a planet" in outcome.note
    assert outcome.metrics["secondary_ppm"] < outcome.metrics["max_occultation_ppm"]


K_DWARF_TEFF = Measurement(value=4100.0, err_lower=100.0, err_upper=100.0)  # 0.65 Rsun, 0.63 Msun


def test_eclipsing_binary_secondary_is_rejected() -> None:
    """A 300 ppm secondary (half the primary) around a K dwarf is far deeper than any
    planet's occultation at P = 3.2 d."""
    inputs = replace(
        make_inputs(odd_depth=600e-6, even_depth=600e-6, sec_depth=300e-6),
        stellar_teff=K_DWARF_TEFF,
    )
    statuses = run(inputs)
    assert statuses["secondary"] == "fail", statuses
    assert vetting_verdict(statuses) == "false_positive"


def test_third_harmonic_rotator_is_rejected() -> None:
    inputs = make_inputs(odd_depth=450e-6, even_depth=450e-6)
    wave = 250e-6 * np.cos(2.0 * np.pi * (inputs.time - 1468.81) / (PERIOD / 3.0))
    statuses = run(with_flux(inputs, inputs.flux - wave, inputs.flux - 5.0 * wave))
    assert statuses["rotation"] == "fail"
    assert vetting_verdict(statuses) != "candidate"


def test_multi_harmonic_spot_is_rejected() -> None:
    """Each harmonic stays below 0.32 of the depth, but together they make a spot bump."""
    inputs = make_inputs(odd_depth=450e-6, even_depth=450e-6)
    phi = 2.0 * np.pi * (inputs.time - T0) / PERIOD
    bump = 95e-6 * (np.sin(phi) - np.cos(2 * phi) - np.sin(3 * phi) + np.cos(4 * phi))
    statuses = run(with_flux(inputs, inputs.flux + bump))
    assert statuses["rotation"] == "fail"


def test_two_glitches_are_rejected_by_coherence() -> None:
    inputs = make_inputs(odd_depth=120e-6, even_depth=120e-6)
    flux = inputs.flux.copy()
    last = inputs.sector == 98
    epoch = np.round((inputs.time - T0) / PERIOD).astype(int)
    phase = (inputs.time - T0) - epoch * PERIOD
    glitch_epochs = sorted(set(epoch[last & (np.abs(phase) <= 0.036)]))[:2]
    for ep in glitch_epochs:
        flux[last & (epoch == ep) & (np.abs(phase) <= 0.036)] -= 4500e-6
    statuses = run(with_flux(inputs, flux))
    assert statuses["coherence"] == "fail"
    assert vetting_verdict(statuses) != "candidate"


def test_inverted_planet_is_not_a_candidate() -> None:
    """Inverted, the transits become bumps: at the planet's own ephemeris nothing passes."""
    inputs = make_inputs()
    statuses = run(with_flux(inputs, 2.0 - inputs.flux))
    assert vetting_verdict(statuses) != "candidate"
    assert statuses["coherence"] == "fail"


def test_detection_gate_uses_sde_only() -> None:
    cfg = CONFIG.gates.detection
    fn = gate_spec("detection").fn  # type: ignore[union-attr]
    base = make_inputs()
    # SNR below the inverted floor no longer decides: SDE is the rule.
    assert fn(replace(base, sde=12.0, snr=5.0, inverted_snr_max=14.0), PARAMS, cfg).status == "pass"
    low = fn(replace(base, sde=7.0, snr=40.0, inverted_snr_max=3.0), PARAMS, cfg)
    assert low.status == "fail"
    assert "below sde_min" in low.note
    assert fn(replace(base, sde=None), PARAMS, cfg).status == "not_evaluable"


@pytest.mark.parametrize(
    ("radius_rjup", "err_rjup", "status"),
    [
        (1.2, 0.05, "pass"),
        (1.8, 0.05, "marginal"),  # bigger than 99% of known planets
        (2.14, 0.025, "marginal"),  # a confirmed planet like HAT-P-67 b never fails
        (2.6, 0.2, "marginal"),  # the interval crosses the largest confirmed planet
        (3.2, 0.1, "fail"),  # even the lower end is above every confirmed planet
    ],
)
def test_plausibility_radius_thresholds(radius_rjup: float, err_rjup: float, status: str) -> None:
    def m(value: float, err: float) -> Measurement:
        return Measurement(value=value, err_lower=err, err_upper=err)

    model = ModelInfo(
        rp_rs=m(0.1, 0.001),
        planet_radius_rearth=m(radius_rjup * RJUP_IN_REARTH, err_rjup * RJUP_IN_REARTH),
        duration_hours=m(1.728, 0.01),
        method="quick",
    )
    outcome = gate_spec("plausibility").fn(  # type: ignore[union-attr]
        replace(make_inputs(), model=model), PARAMS, CONFIG.gates.plausibility
    )
    assert outcome.status == status, outcome.note


def test_a_failed_fit_makes_plausibility_marginal_not_fail() -> None:
    model = ModelInfo(None, None, None, "quick", failure="impossible geometry: a/R* = 0.8")
    outcome = gate_spec("plausibility").fn(  # type: ignore[union-attr]
        replace(make_inputs(), model=model), PARAMS, CONFIG.gates.plausibility
    )
    assert outcome.status == "marginal", outcome.note
    assert "failed fit" in outcome.note


def one_sector(inputs: GateInputs, end: float | None = None) -> GateInputs:
    keep = inputs.sector == inputs.raw[0].sector
    if end is not None:
        keep &= inputs.time < end
    return replace(
        inputs,
        time=inputs.time[keep],
        flux=inputs.flux[keep],
        flux_err=inputs.flux_err[keep],
        sector=inputs.sector[keep],
        raw=(inputs.raw[0],),
    )


def test_coverage_passes_with_enough_transits_in_a_single_sector() -> None:
    cfg = CONFIG.gates.coverage
    outcome = gate_spec("coverage").fn(one_sector(make_inputs()), PARAMS, cfg)  # type: ignore[union-attr]
    assert outcome.status == "pass", outcome.note
    assert "single sector" in outcome.note
    few = gate_spec("coverage").fn(one_sector(make_inputs(), end=1478.0), PARAMS, cfg)  # type: ignore[union-attr]
    assert few.status == "fail", few.note


# A 480 ppm dip carried by a star 40 arcsec away shifts the centroid by 480e-6 * 40 arcsec,
# 0.0192 arcsec or 0.000914 pixel.
NEB_SHIFT_PIX = 480e-6 * 40.0 / 21.0


def test_centroid_rejects_an_eclipse_on_a_neighbor_that_can_make_it() -> None:
    inputs = replace(
        make_inputs(centroid_shift_pix=NEB_SHIFT_PIX), target_tmag=10.0, neighbors=((40.0, 14.0),)
    )
    statuses = run(inputs)
    assert statuses["centroid"] == "fail", statuses
    assert vetting_verdict(statuses) == "false_positive"


def test_centroid_without_a_possible_source_is_only_marginal() -> None:
    inputs = replace(
        make_inputs(centroid_shift_pix=NEB_SHIFT_PIX), target_tmag=10.0, neighbors=((40.0, 22.0),)
    )  # far too faint to make a 480 ppm dip
    statuses = run(inputs)
    assert statuses["centroid"] == "marginal", statuses
    assert vetting_verdict(statuses) == "inconclusive"


def test_odd_even_uses_welch_and_asks_more_of_few_transits() -> None:
    cfg = CONFIG.gates.odd_even
    gate = gate_spec("odd-even").fn  # type: ignore[union-attr]
    eb = gate(make_inputs(odd_depth=950e-6, even_depth=200e-6), PARAMS, cfg)
    assert eb.status == "fail", eb.note
    assert eb.value < cfg.fail_p
    # Two odd and two even transits 30 percent apart: not enough to call it a binary.
    few = gate(
        one_sector(make_inputs(odd_depth=560e-6, even_depth=400e-6), end=1481.5), PARAMS, cfg
    )
    assert few.metrics["n_odd"] + few.metrics["n_even"] <= 5
    assert few.status != "fail", few.note
