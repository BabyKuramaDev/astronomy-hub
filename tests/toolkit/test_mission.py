from pathlib import Path

import pytest
import yaml

from shared.mission import MissionError, load_mission

REAL = Path(__file__).resolve().parents[2] / "missions"


def test_exoplanets_mission_validates() -> None:
    mission = load_mission("exoplanets")
    assert mission.acquisition.sector_selection.rule == "longest_consecutive_run"
    assert mission.detection.snr_min == 8.0


def _write(tmp_path: Path, raw: dict) -> Path:
    (tmp_path / "exoplanets").mkdir()
    (tmp_path / "exoplanets" / "mission.yaml").write_text(yaml.safe_dump(raw))
    return tmp_path


@pytest.fixture
def raw() -> dict:
    return yaml.safe_load((REAL / "exoplanets" / "mission.yaml").read_text())


def test_unknown_mission(tmp_path: Path) -> None:
    with pytest.raises(MissionError, match="unknown mission"):
        load_mission("astrology", tmp_path)


def test_unknown_key_is_rejected(tmp_path: Path, raw: dict) -> None:
    raw["detection"]["typo_threshold"] = 1
    with pytest.raises(MissionError, match=r"detection\.typo_threshold"):
        load_mission("exoplanets", _write(tmp_path, raw))


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("detection", "snr_min", -1),
        ("detection", "period_min_days", 20.0),
        ("modeling", "jitter_ppm_range", [5.0, 1.0]),
        ("acquisition", "flux_column", "SAP_FLUX"),
        ("preparation", "detrend_method", "median"),
    ],
)
def test_invalid_values_are_rejected(
    tmp_path: Path, raw: dict, section: str, key: str, value: object
) -> None:
    raw[section][key] = value
    with pytest.raises(MissionError):
        load_mission("exoplanets", _write(tmp_path, raw))


def test_name_must_match_directory(tmp_path: Path, raw: dict) -> None:
    raw["name"] = "other"
    with pytest.raises(MissionError, match="expected"):
        load_mission("exoplanets", _write(tmp_path, raw))
