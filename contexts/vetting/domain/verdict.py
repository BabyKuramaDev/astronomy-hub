"""How runs combine into a gate status, and gate statuses into the vetting verdict."""

from collections.abc import Sequence
from dataclasses import dataclass


def combine(statuses: Sequence[str]) -> str:
    """All runs pass: pass. All fail: fail. Any mixture (or a marginal run): marginal."""
    if not statuses:
        raise ValueError("a gate needs at least one run")
    if all(s == "pass" for s in statuses):
        return "pass"
    if all(s == "fail" for s in statuses):
        return "fail"
    return "marginal"


@dataclass(frozen=True)
class GateStatus:
    id: str
    status: str
    severity: str  # "hard" | "soft" | "info"


def verdict(gates: Sequence[GateStatus]) -> str:
    """A hard fail: false_positive. A soft fail or any marginal: inconclusive.
    Everything passing: candidate. Info gates never count."""
    counted = [g for g in gates if g.severity != "info"]
    if not counted:
        raise ValueError("no gate enters the verdict")
    if any(g.severity == "hard" and g.status == "fail" for g in counted):
        return "false_positive"
    if any(g.status != "pass" for g in counted):
        return "inconclusive"
    return "candidate"
