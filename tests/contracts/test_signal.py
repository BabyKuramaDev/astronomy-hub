from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import SignalData
from shared.contracts.signal import DETECTION_FIELDS


def test_detected_signal_is_valid(detected_signal: dict[str, Any]) -> None:
    signal = SignalData.model_validate(detected_signal)
    assert signal.period_days == pytest.approx(0.9414)
    assert signal.other_peaks[0].period_days == pytest.approx(1.8828)


def test_no_signal_is_valid_with_null_detection_fields(no_signal: dict[str, Any]) -> None:
    signal = SignalData.model_validate(no_signal)
    dumped = signal.model_dump(mode="json")
    assert all(dumped[name] is None for name in DETECTION_FIELDS)


def test_no_signal_may_list_subthreshold_peaks(no_signal: dict[str, Any]) -> None:
    peaks = [{"period_days": 3.1, "snr": 5.2, "depth_ppm": 300.0}]
    assert SignalData.model_validate({**no_signal, "other_peaks": peaks}).other_peaks


@pytest.mark.parametrize("name", DETECTION_FIELDS)
def test_detected_requires_every_detection_field(
    detected_signal: dict[str, Any], name: str
) -> None:
    with pytest.raises(ValidationError, match=name):
        SignalData.model_validate({**detected_signal, name: None})


@pytest.mark.parametrize("name", DETECTION_FIELDS)
def test_not_detected_requires_null_detection_fields(
    detected_signal: dict[str, Any], no_signal: dict[str, Any], name: str
) -> None:
    with pytest.raises(ValidationError, match=name):
        SignalData.model_validate({**no_signal, name: detected_signal[name]})


@pytest.mark.parametrize("name", ["sectors", "method", "other_peaks", "detected"])
def test_always_present_fields_are_required(no_signal: dict[str, Any], name: str) -> None:
    data = dict(no_signal)
    del data[name]
    with pytest.raises(ValidationError):
        SignalData.model_validate(data)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("period_days", 0.0),
        ("period_days", -1.0),
        ("period_days", float("nan")),
        ("period_days", float("inf")),
        ("duration_hours", 0.0),
        ("depth_ppm", -10.0),
        ("snr", -0.1),
        ("n_transits", 0),
        ("sectors", []),
        ("sectors", [0]),
        ("sectors", [2, 2]),
        ("method", ""),
    ],
)
def test_out_of_range_values_are_rejected(
    detected_signal: dict[str, Any], name: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        SignalData.model_validate({**detected_signal, name: value})


def test_peak_shape_is_closed(no_signal: dict[str, Any]) -> None:
    peak = {"period_days": 3.1, "snr": 5.2, "depth_ppm": 300.0, "power": 1.0}
    with pytest.raises(ValidationError):
        SignalData.model_validate({**no_signal, "other_peaks": [peak]})
