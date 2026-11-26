from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import ReproductionData, ReviewData


@pytest.fixture
def review_data() -> dict[str, Any]:
    return {
        "period_days_independent": 0.94145,
        "depth_ppm_independent": 9300.0,
        "disagreements": [],
        "verdict": "reproduced",
        "period_ratio": 1.0,
        "depth_ratio": 0.98,
        "rationale": "TLS finds the same period and depth.",
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
            "period_ratio": None,
            "depth_ratio": None,
            "rationale": "Nothing above the SDE threshold.",
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
            "period_ratio": 1.0,
            "depth_ratio": None,
            "rationale": "Same period, depth unclear.",
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


def test_rationale_is_required(review_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ReviewData.model_validate({**review_data, "rationale": ""})


@pytest.fixture
def reproduction() -> dict[str, Any]:
    return {
        "detrend_method": "median",
        "detrend_window_days": 1.0,
        "search_method": "tls",
        "sectors": [103, 104],
        "period_min_days": 0.5,
        "period_max_days": 3.0,
        "detected": True,
        "sde_min": 9.0,
        "period_days": 0.9414,
        "epoch_btjd": 3300.1,
        "duration_hours": 2.1,
        "depth_ppm": 9800.0,
        "sde": 40.0,
        "snr": 300.0,
        "n_transits": 10,
    }


def test_reproduction(reproduction: dict[str, Any]) -> None:
    assert ReproductionData.model_validate(reproduction).detected
    blank = {k: None for k in ("period_days", "epoch_btjd", "duration_hours", "depth_ppm")}
    none = {**reproduction, **blank, "sde": None, "snr": None, "n_transits": None}
    assert not ReproductionData.model_validate({**none, "detected": False}).detected
    with pytest.raises(ValidationError, match="detected=true"):
        ReproductionData.model_validate(none)
