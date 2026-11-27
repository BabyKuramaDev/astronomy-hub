import json
from pathlib import Path

from evals.index import Index, version_key
from evals.outcomes import from_agent_run, from_dossier
from evals.scoring import Outcome, alias, compare, period_match, score

LABELS = [
    {"tic_id": 1, "group": "planet_deep", "split": "dev", "period_days": 2.0},
    {"tic_id": 2, "group": "planet_small", "split": "dev", "period_days": 3.0},
    {"tic_id": 3, "group": "false_positive", "split": "dev", "period_days": 4.0},
    {"tic_id": 4, "group": "no_signal", "split": "dev", "period_days": None},
    {"tic_id": 5, "group": "planet_deep", "split": "dev", "period_days": 5.0},
    {"tic_id": 6, "group": "no_signal", "split": "dev", "period_days": None},
]


def ok(tic: int, final: str, period: float | None, detected: bool = True) -> Outcome:
    return Outcome(tic, "ok", detected=detected, period_days=period, final=final)


def test_period_and_alias() -> None:
    assert period_match(2.01, 2.0)
    assert not period_match(2.05, 2.0)
    assert alias(4.0, 2.0) == "2/1"
    assert alias(1.0, 3.0) == "1/3"
    assert alias(2.5, 2.0) is None


def test_score_buckets() -> None:
    outcomes = {
        1: ok(1, "candidate", 2.0),
        2: ok(2, "candidate", 6.0),  # right star, alias period
        3: ok(3, "candidate", 4.0),  # false positive accepted
        4: ok(4, "inconclusive", 1.3),  # detection on a quiet star: listed for review
        5: ok(5, "false_positive", 5.0),  # grave error
        6: Outcome(6, "no_data"),
    }
    result = score(LABELS, outcomes)
    rows = {r["group"]: r for r in result["table"]}
    assert rows["planet_deep"]["final_recall"] == 0.5
    assert rows["planet_deep"]["detection_recall"] == 1.0
    assert rows["planet_small"]["candidate_wrong_period"] == 1
    assert rows["false_positive"]["false_positive_accepted"] == 1.0
    assert rows["no_signal"]["detections_to_review"] == [4]
    assert rows["no_signal"]["false_alarm"] == 0.0
    assert rows["no_signal"]["n"] == 1  # the no-data star is apart
    assert [g["tic_id"] for g in result["grave_errors"]] == [5]
    assert result["aliases"] == [{"tic_id": 2, "group": "planet_small", "ratio": "2/1"}]
    assert result["apart"] == [{"tic_id": 6, "group": "no_signal", "status": "no_data", "flags": 0}]


def test_compare_with_baseline() -> None:
    agent = {
        1: ok(1, "candidate", 2.0),
        3: ok(3, "false_positive", 4.0),
        4: ok(4, "no_signal", None),
    }
    base = {
        1: ok(1, "inconclusive", 2.0),
        3: ok(3, "false_positive", 4.0),
        4: ok(4, "no_signal", None, detected=False),
    }
    diff = compare(LABELS, agent, base)
    assert [(d["tic_id"], d["effect"]) for d in diff] == [(1, "better"), (4, "same")]


def write(root: Path, name: str, data: dict) -> None:
    (root / name).write_text(json.dumps({"data": data}))


def test_outcomes_from_files(tmp_path: Path) -> None:
    root = tmp_path / "7"
    root.mkdir()
    (root / "log.jsonl").write_text(
        json.dumps({"tool": "fetch-lightcurves", "exit_code": 3}) + "\n"
    )
    assert from_dossier(7, root).status == "no_data"
    write(root, "signal.json", {"detected": True, "period_days": 2.0})
    write(root, "decision.json", {"final": "candidate"})
    write(root, "vetting.json", {"verdict": "candidate"})
    out = from_dossier(7, root)
    assert (out.status, out.final, out.period_days, out.vetting, out.review) == (
        "ok",
        "candidate",
        2.0,
        "candidate",
        None,
    )
    summary = {
        "tic_id": 7,
        "dossier": str(root),
        "list_cost_cents": 40,
        "run_id": "r",
        "audit": {"flags": [{"before_decide": False}, {"before_decide": True}]},
    }
    agent = from_agent_run(summary)
    assert (agent.status, agent.flags, agent.cost_cents) == ("contaminated", 1, 40)


def test_index_resumes(tmp_path: Path) -> None:
    index = Index(tmp_path / "i.jsonl")
    key = version_key(commit="a", tic_set="s")
    index.add(key, ok(1, "candidate", 2.0))
    index.add(version_key(commit="b", tic_set="s"), ok(2, "candidate", 2.0))
    assert index.done(key) == {1}
    assert index.outcomes(key)[1].final == "candidate"


def test_index_can_redo_incomplete(tmp_path: Path) -> None:
    index = Index(tmp_path / "i.jsonl")
    index.add("k", Outcome(1, "incomplete"))
    index.add("k", Outcome(2, "incomplete"))
    index.add("k", ok(2, "candidate", 2.0))  # redone later: the last row counts
    assert index.done("k") == {1, 2}
    assert index.done("k", redo_incomplete=True) == {2}
