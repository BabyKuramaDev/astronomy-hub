"""What the Managed Agents runs have cost, kept in runs/ledger.jsonl, and the spend caps.

Each entry carries its milestone; a cap applies to one milestone (entries written
before milestones were recorded belong to M3).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

MILESTONE = "M4"


class SpendCapError(RuntimeError):
    """Starting another session could take the spend past the cap."""


def spent_cents(ledger: Path, milestone: str | None = None) -> int:
    if not ledger.exists():
        return 0
    total = 0
    for line in ledger.read_text().splitlines():
        entry = json.loads(line)
        if milestone is None or entry.get("milestone", "M3") == milestone:
            total += int(entry["list_cost_cents"])
    return total


def check_cap(
    ledger: Path,
    cap_cents: int,
    budget_cents: int,
    milestone: str = MILESTONE,
    reserved_cents: int = 0,
) -> int:
    """Raise unless spend so far, sessions in flight and this budget stay within the cap."""
    spent = spent_cents(ledger, milestone)
    if spent + reserved_cents + budget_cents > cap_cents:
        raise SpendCapError(
            f"{milestone}: spent {spent / 100:.2f} USD "
            f"(+{reserved_cents / 100:.2f} in flight) of a "
            f"{cap_cents / 100:.2f} USD cap; a session with a {budget_cents / 100:.2f} USD budget "
            "could go past it"
        )
    return spent


def record(
    ledger: Path,
    run_id: str,
    session_id: str,
    list_cost_cents: int,
    kind: str,
    milestone: str = MILESTONE,
) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "session_id": session_id,
        "kind": kind,
        "milestone": milestone,
        "list_cost_cents": list_cost_cents,
    }
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
