from typing import Any

import pytest

SHA = "sha256:" + "0" * 64


def envelope(data: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": "0.1.0",
        "tic_id": 100100827,
        "mission": "exoplanets",
        "produced_by": {"context": "detection", "tool": "search-period", "version": "0.1.0"},
        "created_at": "2026-11-26T12:00:00Z",
        "inputs": {"lightcurve_clean.parquet": SHA},
        "data": data,
    }
    base.update(overrides)
    return base


@pytest.fixture
def detected_signal() -> dict[str, Any]:
    return {
        "detected": True,
        "period_days": 0.9414,
        "epoch_btjd": 1354.4578,
        "duration_hours": 2.2,
        "depth_ppm": 9500.0,
        "snr": 120.5,
        "n_transits": 25,
        "sectors": [2, 3],
        "method": "bls",
        "other_peaks": [{"period_days": 1.8828, "snr": 40.1, "depth_ppm": 4700.0}],
    }


@pytest.fixture
def no_signal() -> dict[str, Any]:
    return {"detected": False, "sectors": [2], "method": "bls", "other_peaks": []}
