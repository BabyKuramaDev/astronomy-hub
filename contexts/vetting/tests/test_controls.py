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
    assert statuses.pop("catalog") == "marginal"  # no catalog.json: info only
    assert set(statuses.values()) == {"pass"}, statuses
    assert vetting_verdict(run(make_inputs())) == "candidate"


@pytest.mark.parametrize(
    ("kwargs", "gate", "expected_verdict"),
    [
        ({"odd_depth": 950e-6, "even_depth": 200e-6}, "odd-even", "false_positive"),
        (
            {"odd_depth": 600e-6, "even_depth": 600e-6, "sec_depth": 300e-6},
            "secondary",
            "false_positive",
        ),
        ({"drop_last_sector_signal": True}, "holdout", "inconclusive"),
        ({"centroid_shift_pix": 0.20}, "centroid", "false_positive"),
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
    """A planet's occultation (10% of the transit) is significant but must not fail gate 6."""
    inputs = make_inputs(odd_depth=600e-6, even_depth=600e-6, sec_depth=60e-6)
    cfg = CONFIG.gates.secondary
    outcome = gate_spec("secondary").fn(inputs, PARAMS, cfg)  # type: ignore[union-attr]
    assert outcome.value is not None
    assert outcome.value >= cfg.min_sigma
    assert outcome.status == "pass"
    assert "compatible with a planet" in outcome.note
    assert outcome.metrics["depth_ratio"] == pytest.approx(0.1, abs=0.05)


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


def test_snr_gate_uses_the_noise_floor() -> None:
    cfg = CONFIG.gates.snr
    fn = gate_spec("snr").fn  # type: ignore[union-attr]
    base = make_inputs()
    assert fn(replace(base, snr=12.0, inverted_snr_max=10.0), PARAMS, cfg).status == "pass"
    floor = fn(replace(base, snr=12.0, inverted_snr_max=14.0), PARAMS, cfg)
    assert floor.status == "fail"
    assert "noise floor" in floor.note
    assert fn(replace(base, snr=7.0, inverted_snr_max=3.0), PARAMS, cfg).status == "fail"


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
