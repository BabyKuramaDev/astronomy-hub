from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import (
    CONTRACTS,
    DecisionData,
    Envelope,
    SignalData,
    SignalFile,
    canonical_json,
    data_sha256,
)
from tests.contracts.conftest import SHA, envelope


def test_valid_envelope_round_trips_through_json(no_signal: dict[str, Any]) -> None:
    parsed = SignalFile.model_validate(envelope(no_signal))
    assert SignalFile.model_validate_json(parsed.model_dump_json()) == parsed


def test_created_at_is_serialized_in_utc(no_signal: dict[str, Any]) -> None:
    parsed = SignalFile.model_validate(envelope(no_signal))
    assert parsed.model_dump(mode="json")["created_at"] == "2026-11-26T12:00:00Z"


def test_created_at_accepts_explicit_utc_offset(no_signal: dict[str, Any]) -> None:
    created = datetime(2026, 11, 26, 12, tzinfo=UTC)
    parsed = SignalFile.model_validate(envelope(no_signal, created_at=created))
    assert parsed.created_at == created


@pytest.mark.parametrize(
    "created_at",
    [
        "2026-11-26T12:00:00",  # naive
        "2026-11-26T09:00:00-03:00",  # aware, not UTC
        datetime(2026, 11, 26, 9, tzinfo=timezone(timedelta(hours=-3))),
    ],
)
def test_created_at_must_be_utc(no_signal: dict[str, Any], created_at: Any) -> None:
    with pytest.raises(ValidationError):
        SignalFile.model_validate(envelope(no_signal, created_at=created_at))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "0.1"),
        ("schema_version", "v0.1.0"),
        ("tic_id", 0),
        ("tic_id", -5),
        ("mission", ""),
        ("mission", "Exoplanets"),
        ("produced_by", {"context": "astrology", "tool": "x", "version": "1"}),
        ("produced_by", {"context": "detection", "tool": "Search Period", "version": "1"}),
        ("produced_by", {"context": "detection", "tool": "search-period", "version": ""}),
        ("inputs", {"signal.json": "md5:abc"}),
        ("inputs", {"signal.json": "sha256:" + "A" * 64}),
        ("inputs", {"/abs/signal.json": SHA}),
        ("inputs", {"../other/signal.json": SHA}),
        ("inputs", {"lightcurve\\s1.fits": SHA}),
        ("inputs", {"": SHA}),
    ],
)
def test_invalid_envelope_fields_are_rejected(
    no_signal: dict[str, Any], field: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        SignalFile.model_validate(envelope(no_signal, **{field: value}))


def test_nested_input_paths_are_allowed(no_signal: dict[str, Any]) -> None:
    parsed = SignalFile.model_validate(envelope(no_signal, inputs={"lightcurve/s0002.fits": SHA}))
    assert "lightcurve/s0002.fits" in parsed.inputs


def test_unknown_envelope_field_is_rejected(no_signal: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SignalFile.model_validate({**envelope(no_signal), "extra": 1})


def test_envelope_is_immutable(no_signal: dict[str, Any]) -> None:
    parsed = SignalFile.model_validate(envelope(no_signal))
    with pytest.raises(ValidationError):
        parsed.tic_id = 2  # type: ignore[misc]


def test_data_must_match_the_file_contract(no_signal: dict[str, Any]) -> None:
    decision = {
        "mode": "eval",
        "final": "no_signal",
        "reason": "No peak above threshold.",
        "next_step": "None.",
    }
    with pytest.raises(ValidationError):
        SignalFile.model_validate(envelope(decision))
    assert Envelope[DecisionData].model_validate(envelope(decision)).data.final == "no_signal"


def test_data_hash_ignores_envelope_metadata(no_signal: dict[str, Any]) -> None:
    first = SignalFile.model_validate(envelope(no_signal))
    second = SignalFile.model_validate(
        envelope(
            no_signal,
            created_at="2027-01-01T00:00:00Z",
            produced_by={"context": "detection", "tool": "search-period", "version": "9.9.9"},
            inputs={},
        )
    )
    assert data_sha256(first) == data_sha256(second)


def test_data_hash_changes_with_data(no_signal: dict[str, Any]) -> None:
    first = SignalFile.model_validate(envelope(no_signal))
    second = SignalFile.model_validate(envelope({**no_signal, "sectors": [3]}))
    assert data_sha256(first) != data_sha256(second)


def test_data_hash_has_digest_format(no_signal: dict[str, Any]) -> None:
    digest = data_sha256(SignalFile.model_validate(envelope(no_signal)))
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_canonical_json_is_key_order_independent() -> None:
    a = SignalData.model_validate(
        {"detected": False, "sectors": [1], "method": "bls", "other_peaks": []}
    )
    b = SignalData.model_validate(
        {"other_peaks": [], "method": "bls", "sectors": [1], "detected": False}
    )
    assert canonical_json(a) == canonical_json(b)
    assert b" " not in canonical_json(a)


def test_contract_registry_covers_every_fixed_dossier_file() -> None:
    assert set(CONTRACTS) == {
        "lightcurve/manifest.json",
        "star.json",
        "search.json",
        "signal.json",
        "model.json",
        "catalog.json",
        "vetting/runs.json",
        "vetting.json",
        "review/reproduction.json",
        "review.json",
        "ephemeris.json",
        "decision.json",
    }
