import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from shared.contracts import DecisionData, Envelope, LogEntry, data_sha256
from shared.kernel.contexts import Context
from shared.toolkit.dossier import Dossier, sha256_file
from shared.toolkit.errors import DataNotAvailableError, InvalidInputError
from shared.toolkit.meta import ToolMeta


def meta() -> ToolMeta:
    return ToolMeta(
        context=Context.DIRECTION,
        tool="decide",
        tic_id=7,
        mission="exoplanets",
        version="0.1.0",
        clock=lambda: datetime(2026, 11, 26, tzinfo=UTC),
    )


def decision() -> DecisionData:
    return DecisionData(mode="eval", final="no_signal", reason="No peak.", next_step="None.")


def test_dossier_location(tmp_path: Path) -> None:
    dossier = Dossier.for_target(tmp_path, "exoplanets", 7)
    assert dossier.root == tmp_path / "exoplanets" / "7"
    assert dossier.cache_dir == dossier.root / ".cache"


def test_envelope_round_trip_records_hashes(tmp_path: Path) -> None:
    dossier = Dossier(tmp_path)
    env = meta().envelope(decision(), {"b.json": "sha256:" + "0" * 64})
    digest = dossier.write_envelope("decision.json", env)
    assert digest == data_sha256(env)
    assert dossier.writes == {"decision.json": digest}

    reader = Dossier(tmp_path)
    loaded = reader.read_envelope("decision.json", Envelope[DecisionData])
    assert loaded == env
    assert reader.reads["decision.json"] == sha256_file(tmp_path / "decision.json")


def test_rewriting_same_data_gives_same_hash(tmp_path: Path) -> None:
    first = meta().envelope(decision(), {})
    later = ToolMeta(**{**meta().__dict__, "clock": lambda: datetime(2030, 1, 1, tzinfo=UTC)})
    a = Dossier(tmp_path).write_envelope("d.json", first)
    b = Dossier(tmp_path).write_envelope("d.json", later.envelope(decision(), {}))
    assert a == b


def test_missing_file_is_data_not_available(tmp_path: Path) -> None:
    with pytest.raises(DataNotAvailableError, match=r"signal\.json"):
        Dossier(tmp_path).read_envelope("signal.json", Envelope[DecisionData])


def test_invalid_contract_is_invalid_input(tmp_path: Path) -> None:
    (tmp_path / "decision.json").write_text(json.dumps({"tic_id": 1}))
    with pytest.raises(InvalidInputError, match="contract"):
        Dossier(tmp_path).read_envelope("decision.json", Envelope[DecisionData])


def test_paths_cannot_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="relative"):
        Dossier(tmp_path).path("../outside.json")


def test_table_round_trip_is_deterministic(tmp_path: Path) -> None:
    columns = {"time_btjd": np.array([1.0, 2.0]), "sector": np.array([2, 2], dtype=np.int16)}
    first = Dossier(tmp_path).write_table("t.parquet", columns)
    second = Dossier(tmp_path).write_table("t.parquet", columns)
    assert first == second
    reader = Dossier(tmp_path)
    loaded = reader.read_table("t.parquet")
    np.testing.assert_array_equal(loaded["time_btjd"], columns["time_btjd"])
    assert loaded["sector"].dtype == np.int16
    assert "t.parquet" in reader.reads


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    Dossier(tmp_path).write_bytes("figures/a.png", b"png")
    assert sorted(p.name for p in (tmp_path / "figures").iterdir()) == ["a.png"]


def test_append_log(tmp_path: Path) -> None:
    dossier = Dossier(tmp_path / "new")
    entry = LogEntry(
        ts=datetime(2026, 11, 26, tzinfo=UTC),
        context=Context.DETECTION,
        tool="fold",
        argv=["fold"],
        version="0.1.0",
        duration_s=0.1,
        exit_code=0,
        outputs={},
        summary=None,
        reason=None,
        error=None,
    )
    dossier.append_log(entry)
    dossier.append_log(entry)
    lines = (tmp_path / "new" / "log.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert LogEntry.model_validate_json(lines[0]) == entry
