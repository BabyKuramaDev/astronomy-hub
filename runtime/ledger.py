"""What the Managed Agents runs have cost, kept in runs/ledger.jsonl, and the spend cap."""

import json
from datetime import UTC, datetime
from pathlib import Path


class SpendCapError(RuntimeError):
    """Starting another session could take the total spend past the cap."""


def spent_cents(ledger: Path) -> int:
    if not ledger.exists():
        return 0
    return sum(int(json.loads(line)["list_cost_cents"]) for line in ledger.read_text().splitlines())


def check_cap(ledger: Path, cap_cents: int, budget_cents: int) -> int:
    """Raise unless the spend so far plus this session's budget stays within the cap."""
    spent = spent_cents(ledger)
    if spent + budget_cents > cap_cents:
        raise SpendCapError(
            f"spent {spent / 100:.2f} USD of a {cap_cents / 100:.2f} USD cap; a session with a "
            f"{budget_cents / 100:.2f} USD budget could go past it"
        )
    return spent


def record(ledger: Path, run_id: str, session_id: str, list_cost_cents: int, kind: str) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "session_id": session_id,
        "kind": kind,
        "list_cost_cents": list_cost_cents,
    }
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
