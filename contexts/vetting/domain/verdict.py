"""How runs combine into a gate status, and gate statuses into the vetting verdict."""

from collections.abc import Sequence
from dataclasses import dataclass


def combine(statuses: Sequence[str]) -> str:
    """All runs pass: pass. All fail: fail. All not evaluable: not_evaluable. Runs that
    could not be evaluated are otherwise ignored; any other mixture is marginal."""
    if not statuses:
        raise ValueError("a gate needs at least one run")
    measured = [s for s in statuses if s != "not_evaluable"]
    if not measured:
        return "not_evaluable"
    if all(s == "pass" for s in measured):
        return "pass"
    if all(s == "fail" for s in measured):
        return "fail"
    return "marginal"


@dataclass(frozen=True)
class GateStatus:
    id: str
    status: str
    severity: str  # "hard" | "soft" | "info"


def verdict(gates: Sequence[GateStatus]) -> str:
    """A hard fail: false_positive. Candidate when tier() gives A or B. Anything else
    (a hard gate marginal or not evaluable, a soft fail): inconclusive. Info never counts."""
    counted = [g for g in gates if g.severity != "info"]
    if not counted:
        raise ValueError("no gate enters the verdict")
    if any(g.severity == "hard" and g.status == "fail" for g in counted):
        return "false_positive"
    return "candidate" if tier(gates) is not None else "inconclusive"


def tier(gates: Sequence[GateStatus]) -> str | None:
    """A: every counted gate passes. B: no hard gate fails, is marginal or could not be
    evaluated, no soft gate fails, and the rest are soft marginals or soft gates that
    could not be evaluated (a single sector, for example). None otherwise."""
    counted = [g for g in gates if g.severity != "info"]
    if all(g.status == "pass" for g in counted):
        return "A"
    for g in counted:
        if g.status == "pass":
            continue
        if g.severity == "hard" or g.status == "fail":
            return None
    return "B"
