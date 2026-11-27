import json
from pathlib import Path

import pytest

from evals.scoring import Outcome
from runtime.eval_agents import Budget, retryable
from runtime.ledger import SpendCapError, record, spent_cents


def test_budget_counts_sessions_in_flight(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    record(ledger, "r0", "s0", 300, "eval-pilot", "M4")
    with ledger.open("a") as handle:  # entries from before milestones were recorded are M3
        handle.write(json.dumps({"run_id": "old", "list_cost_cents": 900}) + "\n")
    assert (spent_cents(ledger, "M4"), spent_cents(ledger, "M3")) == (300, 900)
    budget = Budget(ledger, cap_cents=1000, budget_cents=200, milestone="M4")
    assert [budget.reserve() for _ in range(3)] == [0, 200, 400]
    with pytest.raises(SpendCapError):
        budget.reserve()  # 300 spent + 600 in flight + 200 > 1000
    budget.release()
    assert budget.reserve() == 400


@pytest.mark.parametrize(
    ("stop", "status", "events", "expected"),
    [
        ("terminated", "incomplete", "", True),
        ("budget_reached", "incomplete", "", False),  # out of budget: never retried
        ("end_turn", "incomplete", "bin/hub acquisition fetch-lightcurves ... HTTPError 503", True),
        ("end_turn", "ok", "", False),
        ("stream_lost", "no_data", "", False),
    ],
)
def test_retryable(stop: str, status: str, events: str, expected: bool) -> None:
    out = Outcome(1, status)
    assert retryable({"stop_reason": stop}, out, json.dumps(events)) is expected


def test_alarms_stop_the_run() -> None:
    from runtime.eval_agents import check_alarm

    planet = {"group": "planet_small", "period_days": 3.0}
    fp = {"group": "false_positive", "period_days": 2.0}
    assert check_alarm(planet, Outcome(1, "contaminated", flags=2), None)
    assert "grave" in (
        check_alarm(planet, Outcome(1, "ok", final="false_positive", period_days=3.01), None) or ""
    )
    assert (
        check_alarm(planet, Outcome(1, "ok", final="false_positive", period_days=1.2), None) is None
    )
    accepted_a = Outcome(2, "ok", final="candidate", tier="A")
    assert "tier A" in (check_alarm(fp, accepted_a, Outcome(2, "ok", final="inconclusive")) or "")
    assert check_alarm(fp, accepted_a, Outcome(2, "ok", final="candidate", tier="A")) is None
    assert check_alarm(fp, Outcome(2, "ok", final="candidate", tier="B"), None) is None


def test_mast_failures_are_recognised_and_waited_out() -> None:
    from runtime.eval_agents import mast_failure, wait_for_mast

    events = '"text": "error: MAST unavailable: product list failed: RemoteServiceError"'
    assert mast_failure(Outcome(1, "incomplete"), events)
    assert not mast_failure(Outcome(1, "ok", final="no_signal"), events)
    answers = iter([False, False, True])
    waits: list[float] = []
    assert wait_for_mast(probe=lambda: next(answers), sleep=waits.append)
    assert len(waits) == 2
    assert not wait_for_mast(probe=lambda: False, sleep=lambda _s: None)
