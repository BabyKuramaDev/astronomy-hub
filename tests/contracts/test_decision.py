import pytest
from pydantic import ValidationError

from shared.contracts import DecisionData


@pytest.mark.parametrize(
    "final", ["no_signal", "known", "false_positive", "candidate", "inconclusive"]
)
def test_final_values(final: str) -> None:
    data = DecisionData(final=final, reason="Because.", next_step="Follow up.")  # type: ignore[arg-type]
    assert data.final == final


@pytest.mark.parametrize(
    ("field", "value"),
    [("final", "planet"), ("reason", ""), ("next_step", "")],
)
def test_invalid_decision_is_rejected(field: str, value: str) -> None:
    data = {"final": "candidate", "reason": "Because.", "next_step": "Follow up."}
    with pytest.raises(ValidationError):
        DecisionData.model_validate({**data, field: value})
