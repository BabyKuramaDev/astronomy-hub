"""Turn a dossier (and, for agent runs, the run summary) into a scoring Outcome."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from evals.scoring import Outcome

NO_DATA_EXIT = 3  # DataNotAvailableError


def _data(root: Path, name: str) -> dict[str, Any] | None:
    path = root / name
    if not path.exists():
        return None
    return json.loads(path.read_text())["data"]


def _log(root: Path) -> list[dict[str, Any]]:
    path = root / "log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def no_data(entries: list[dict[str, Any]]) -> bool:
    fetches = [e for e in entries if e.get("tool") == "fetch-lightcurves"]
    return bool(fetches) and all(e.get("exit_code") == NO_DATA_EXIT for e in fetches)


def from_dossier(tic_id: int, root: Path | None, **extra: Any) -> Outcome:
    if root is None or not root.exists():
        return Outcome(tic_id, "incomplete", **extra)
    signal = _data(root, "signal.json")
    decision = _data(root, "decision.json")
    vetting = _data(root, "vetting.json")
    review = _data(root, "review.json")
    model = _data(root, "model.json")
    log = _log(root)
    fit = (model.get("status") or "fitted") if model else None
    if fit is None and any(e.get("tool") == "fit-transit" and e.get("exit_code") for e in log):
        fit = "crashed"
    if decision is None:
        status = "no_data" if no_data(log) else "incomplete"
        return Outcome(tic_id, status, fit=fit, **extra)
    return Outcome(
        tic_id,
        "ok",
        detected=bool(signal and signal["detected"]),
        period_days=signal.get("period_days") if signal else None,
        final=decision["final"],
        tier=decision.get("tier") or ("A" if decision["final"] == "candidate" else None),
        vetting=vetting["verdict"] if vetting else None,
        review=review["verdict"] if review else None,
        fit=fit,
        **extra,
    )


def contaminating(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Audit flags that could have changed the decision: any before decide."""
    return [f for f in flags if f.get("before_decide")]


def from_agent_run(summary: dict[str, Any], no_data_in_events: bool = False) -> Outcome:
    tic = int(summary["tic_id"])
    dossier = Path(summary["dossier"]) if summary.get("dossier") else None
    flags = contaminating(summary.get("audit", {}).get("flags", []))
    extra = {
        "cost_cents": int(summary.get("list_cost_cents") or 0),
        "active_seconds": float(summary.get("active_seconds") or 0.0),
        "flags": len(flags),
        "run": str(summary.get("run_id")),
    }
    out = from_dossier(tic, dossier, **extra)
    if out.status == "incomplete" and no_data_in_events:
        return Outcome(tic, "no_data", **extra)
    if flags and out.status == "ok":
        return replace(out, status="contaminated")
    return out
