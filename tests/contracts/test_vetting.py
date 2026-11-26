from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import VettingData


def gate(gate_id: str = "snr", **overrides: Any) -> dict[str, Any]:
    base = {
        "id": gate_id,
        "status": "pass",
        "severity": "hard",
        "value": 12.0,
        "threshold": 8.0,
        "note": "Combined BLS SNR above threshold.",
    }
    return {**base, **overrides}


@pytest.fixture
def vetting_data() -> dict[str, Any]:
    return {
        "gates": [gate("snr"), gate("odd-even-depth", status="marginal", severity="soft")],
        "verdict": "inconclusive",
        "rationale": "Odd-even depth is marginal.",
    }


def test_valid_vetting(vetting_data: dict[str, Any]) -> None:
    data = VettingData.model_validate(vetting_data)
    assert [g.status for g in data.gates] == ["pass", "marginal"]


def test_value_and_threshold_may_be_null(vetting_data: dict[str, Any]) -> None:
    gates = [gate("catalog-duplicate", value=None, threshold=None)]
    assert VettingData.model_validate({**vetting_data, "gates": gates})


@pytest.mark.parametrize(
    "bad_gate",
    [
        gate("3"),
        gate("Odd Even"),
        gate("odd_even"),
        gate(status="passed"),
        gate(status=True),
        gate(severity="critical"),
        gate(value=float("nan")),
        {**gate(), "passed": True},
    ],
)
def test_invalid_gate_is_rejected(vetting_data: dict[str, Any], bad_gate: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VettingData.model_validate({**vetting_data, "gates": [bad_gate]})


def test_gate_ids_must_be_unique(vetting_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="unique"):
        VettingData.model_validate({**vetting_data, "gates": [gate("snr"), gate("snr")]})


def test_at_least_one_gate(vetting_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VettingData.model_validate({**vetting_data, "gates": []})


@pytest.mark.parametrize("verdict", ["candidate", "false_positive", "inconclusive"])
def test_verdict_values(vetting_data: dict[str, Any], verdict: str) -> None:
    assert VettingData.model_validate({**vetting_data, "verdict": verdict}).verdict == verdict


def test_unknown_verdict_is_rejected(vetting_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VettingData.model_validate({**vetting_data, "verdict": "reproduced"})
