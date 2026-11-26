"""Acceptance checks of a run and facts read back from its events."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

from shared.contracts import DecisionFile, SignalFile

REPO = Path(__file__).resolve().parent.parent
AGENT_FILES = sorted((REPO / "contexts").glob("*/agent.md"))


def agent_names() -> list[str]:
    names = []
    for path in AGENT_FILES:
        front = path.read_text().split("---\n", 2)[1]
        names.append(str(yaml.safe_load(front)["name"]))
    return names


def tool_output(records: list[dict[str, Any]], marker: str) -> list[str]:
    """Text results of the bash calls whose command contains marker, in order."""
    ids = {
        rec["event"]["id"]
        for rec in records
        if rec["event"].get("type") == "agent.tool_use"
        and marker in str((rec["event"].get("input") or {}).get("command", ""))
    }
    out = []
    for rec in records:
        event = rec["event"]
        if event.get("type") == "agent.tool_result" and event.get("tool_use_id") in ids:
            for block in event.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    out.append(str(block.get("text", "")))
    return out


def setup_report(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The JSON line bin/setup-sandbox printed (python3 version, mode, seconds)."""
    for text in tool_output(records, "bin/setup-sandbox"):
        for match in re.finditer(r"\{[^{}]*\"mode\"[^{}]*\}", text):
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
    return None


def acceptance(
    summary: dict[str, Any], dossier: Path | None, reference_period: float, expected: str
) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    checks["dossier_downloaded"] = dossier is not None
    checks["contracts_valid"] = bool(summary["validated"]) and not summary["validation_errors"]
    final = period = None
    if dossier is not None and (dossier / "decision.json").exists():
        final = DecisionFile.model_validate_json(
            (dossier / "decision.json").read_bytes()
        ).data.final
    if dossier is not None and (dossier / "signal.json").exists():
        period = SignalFile.model_validate_json(
            (dossier / "signal.json").read_bytes()
        ).data.period_days
    checks["final"] = final
    checks["final_as_expected"] = final == expected
    checks["period_days"] = period
    checks["period_within_1_percent"] = (
        period is not None and abs(period / reference_period - 1.0) <= 0.01
    )
    worked = {name for name, row in summary["agents"].items() if row["model_requests"] > 0}
    if expected == "candidate":  # eval: all six agents take part
        missing = sorted(set(agent_names()) - worked)
        checks["agents_missing"] = missing
        checks["six_agents_worked"] = not missing
    checks["passed"] = all(v for k, v in checks.items() if isinstance(v, bool))
    return checks
