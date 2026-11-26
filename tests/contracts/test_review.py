from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import ReviewData


@pytest.fixture
def review_data() -> dict[str, Any]:
    return {
        "period_days_independent": 0.94145,
        "depth_ppm_independent": 9300.0,
        "disagreements": [],
        "verdict": "reproduced",
    }


def test_valid_review(review_data: dict[str, Any]) -> None:
    assert ReviewData.model_validate(review_data).verdict == "reproduced"


@pytest.mark.parametrize("name", ["period_days_independent", "depth_ppm_independent"])
def test_reproduced_requires_independent_values(review_data: dict[str, Any], name: str) -> None:
    with pytest.raises(ValidationError, match="reproduced"):
        ReviewData.model_validate({**review_data, name: None})


def test_not_reproduced_allows_null_values() -> None:
    data = ReviewData.model_validate(
        {
            "period_days_independent": None,
            "depth_ppm_independent": None,
            "disagreements": ["No significant peak found with TLS."],
            "verdict": "not_reproduced",
        }
    )
    assert data.period_days_independent is None


def test_partial_with_period_only() -> None:
    data = ReviewData.model_validate(
        {
            "period_days_independent": 0.9414,
            "depth_ppm_independent": None,
            "disagreements": ["Depth not constrained."],
            "verdict": "partial",
        }
    )
    assert data.verdict == "partial"


@pytest.mark.parametrize("verdict", ["candidate", "false_positive", "inconclusive", "yes"])
def test_vetting_verdicts_are_not_review_verdicts(
    review_data: dict[str, Any], verdict: str
) -> None:
    with pytest.raises(ValidationError):
        ReviewData.model_validate({**review_data, "verdict": verdict})


def test_reproduced_boolean_is_gone(review_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ReviewData.model_validate({**review_data, "reproduced": True})


def test_disagreements_are_non_empty_strings(review_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ReviewData.model_validate({**review_data, "disagreements": [""]})
