"""ManagedAgentsRuntime: one star, one session, one run folder under runs/.

Every event of every thread goes to runs/<run_id>/events.jsonl, the dossier to
runs/<run_id>/<tic>/, and summary.json carries cost and tokens per agent, timing,
the stop reason, agent versions, the commit and the eval-mode command audit.
"""

import json
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from runtime.audit import as_dicts, audit
from runtime.ledger import MILESTONE, check_cap, record
from runtime.outputs import extract, validate
from runtime.ports import Event, Platform, RunMode, RunResult, SessionSpec

FINAL_IDLE = {"end_turn", "budget_reached", "retries_exhausted"}
DENY_MESSAGE = "Runs are unattended: no call can be approved. Use the repository tools instead."


def cents(usage: dict[str, Any] | None) -> int:
    cost = (usage or {}).get("list_cost") or {}
    return int(cost.get("amount") or 0)


def kickoff(tic_id: int, mission: str, mode: RunMode, commit: str) -> str:
    return (
        f"TIC {tic_id}. Mission: {mission}. Mode: {mode}. The repository is mounted at "
        f"/workspace/astronomy-hub at commit {commit}. Follow your instructions."
    )


@dataclass
class RunConfig:
    agent_id: str
    agent_version: int | None
    environment_id: str
    repo_url: str
    commit: str
    runs_dir: Path
    ledger: Path
    cap_cents: int
    kind: str = "hello"
    deadline_s: float = 3600.0
    output_retries: int = 6
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    extra_summary: dict[str, Any] = field(default_factory=dict)
    message: str | None = None  # replaces the kickoff message (the sandbox probe)
    reserved_cents: int = 0  # budgets of sessions already in flight (parallel runners)
    milestone: str = MILESTONE  # whose spend cap this session counts against


class SessionRecorder:
    """Collects events from the primary stream, deduplicated by id."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.seen: set[str] = set()
        self.denied: list[str] = []

    def add(self, event: Event) -> bool:
        key = str(event.get("id") or "")
        if key and key in self.seen:
            return False
        if key:
            self.seen.add(key)
        self.events.append(event)
        return True


@dataclass
class ManagedAgentsRuntime:
    platform: Platform
    config: RunConfig

    def run(self, tic_id: int, mission: str, mode: RunMode, budget_cents: int) -> RunResult:
        cfg = self.config
        check_cap(
            cfg.ledger,
            cfg.cap_cents,
            budget_cents,
            cfg.milestone,
            reserved_cents=cfg.reserved_cents,
        )
        started_wall = datetime.now(UTC)
        run_id = f"{started_wall.strftime('%Y%m%dT%H%M%SZ')}-{tic_id}-{mode}"
        run_dir = cfg.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        spec = SessionSpec(
            agent_id=cfg.agent_id,
            agent_version=cfg.agent_version,
            environment_id=cfg.environment_id,
            repo_url=cfg.repo_url,
            commit=cfg.commit,
            budget_cents=budget_cents,
            title=f"TIC {tic_id} {mode}",
            metadata={
                "tic": str(tic_id),
                "mode": mode,
                "commit": cfg.commit[:12],
                "kind": cfg.kind,
            },
        )
        session_id = self.platform.create_session(spec)
        (run_dir / "session.txt").write_text(session_id + "\n")
        start = cfg.clock()
        recorder = SessionRecorder()
        text = cfg.message or kickoff(tic_id, mission, mode, cfg.commit)
        stop = self._drive(session_id, text, recorder, start)
        wall = cfg.clock() - start

        for event in self.platform.list_events(session_id):  # fill any gap in the stream
            recorder.add(event)
        session = self.platform.session(session_id)
        threads = self.platform.threads(session_id)
        records = self._all_events(session_id, recorder.events, threads)
        with (run_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
            for rec in records:
                handle.write(json.dumps(rec, sort_keys=True) + "\n")

        dossier, validated, errors = self._download(session_id, tic_id, run_dir)
        usage = session.get("usage") or {}
        cost = cents(usage)
        record(cfg.ledger, run_id, session_id, cost, cfg.kind, cfg.milestone)
        flags = audit(records, tic_id)
        summary = {
            "run_id": run_id,
            "session_id": session_id,
            "tic_id": tic_id,
            "mission": mission,
            "mode": mode,
            "commit": cfg.commit,
            "agent": {"id": cfg.agent_id, "version": cfg.agent_version},
            "budget_cents": budget_cents,
            "stop_reason": stop,
            "list_cost_cents": cost,
            "active_seconds": float(usage.get("active_seconds") or 0.0),
            "wall_seconds": round(wall, 1),
            "usage": usage,
            "agents": per_agent(threads, records),
            "denied_tool_calls": recorder.denied,
            "dossier": str(dossier) if dossier else None,
            "validated": validated,
            "validation_errors": errors,
            "audit": {
                "mode": mode,
                "rule": "bash must be bin/hub, bin/setup-sandbox or a read-only command",
                "flags": as_dicts(flags),
            },
            **cfg.extra_summary,
        }
        summary_file = run_dir / "summary.json"
        summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        return RunResult(
            run_id,
            session_id,
            dossier,
            cost,
            summary["active_seconds"],
            round(wall, 1),
            stop,
            summary_file,
        )

    def _drive(self, session_id: str, text: str, recorder: SessionRecorder, start: float) -> str:
        """Stream until the session settles; reconnect and dedupe if the stream drops."""
        sent = False
        for _attempt in range(5):
            try:
                with self.platform.stream(session_id) as stream:
                    if not sent:
                        self.platform.send_message(session_id, text)
                        sent = True
                    else:
                        for event in self.platform.list_events(session_id):
                            recorder.add(event)
                    for event in stream:
                        if not recorder.add(event):
                            continue
                        stop = self._react(session_id, event, recorder)
                        if stop is not None:
                            return stop
                        if self.config.clock() - start > self.config.deadline_s:
                            self.platform.interrupt(session_id)
                            return "deadline"
            except (ConnectionError, TimeoutError, OSError):
                continue
            status = self.platform.session(session_id).get("status")
            if status == "terminated":
                return "terminated"
        return "stream_lost"

    def _react(self, session_id: str, event: Event, recorder: SessionRecorder) -> str | None:
        kind = event.get("type")
        if (
            kind in ("agent.tool_use", "agent.mcp_tool_use")
            and event.get("evaluated_permission") == "ask"
        ):
            self.platform.deny_tool(session_id, str(event["id"]), DENY_MESSAGE)
            recorder.denied.append(str(event["id"]))
        elif kind == "session.status_idle":
            reason = ((event.get("stop_reason") or {}).get("type")) or "unknown"
            if reason in FINAL_IDLE:
                return reason
        elif kind == "session.status_terminated":
            return "terminated"
        return None

    def _all_events(
        self, session_id: str, primary: list[Event], threads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        primary_thread = next((t for t in threads if not t.get("parent_thread_id")), None)
        primary_id = str(primary_thread["id"]) if primary_thread else "primary"
        primary_agent = agent_name(primary_thread) if primary_thread else "Director"
        records = [{"thread_id": primary_id, "agent": primary_agent, "event": e} for e in primary]
        for thread in threads:
            if thread is primary_thread:
                continue
            name = agent_name(thread)
            for event in self.platform.thread_events(session_id, str(thread["id"])):
                records.append({"thread_id": str(thread["id"]), "agent": name, "event": event})
        return records

    def _download(
        self, session_id: str, tic_id: int, run_dir: Path
    ) -> tuple[Path | None, list[str], dict[str, str]]:
        wanted = f"dossier-{tic_id}.tar.gz"
        for attempt in range(self.config.output_retries):
            files = [
                f for f in self.platform.output_files(session_id) if f.get("filename") == wanted
            ]
            if files:
                data = self.platform.download(str(files[0]["id"]))
                (run_dir / wanted).write_bytes(data)
                dossier = extract(data, run_dir)
                validated, errors = validate(dossier)
                return dossier, validated, errors
            if attempt + 1 < self.config.output_retries:
                self.config.sleep(3.0)
        return None, [], {wanted: "not found in the session outputs"}


def agent_name(thread: dict[str, Any] | None) -> str:
    agent = (thread or {}).get("agent") or {}
    return str(agent.get("name") or agent.get("type") or "unknown")


def per_agent(threads: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    """Cost and tokens per agent (threads of the same agent add up) and what each did."""
    out: dict[str, Any] = defaultdict(
        lambda: {
            "threads": 0,
            "list_cost_cents": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "model_requests": 0,
            "tool_calls": 0,
            "model": None,
            "version": None,
        }
    )
    for thread in threads:
        name = agent_name(thread)
        row = out[name]
        usage = thread.get("usage") or {}
        row["threads"] += 1
        row["list_cost_cents"] += cents(usage)
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            row[key] += int(usage.get(key) or 0)
        agent = thread.get("agent") or {}
        model = agent.get("model")
        row["model"] = model.get("id") if isinstance(model, dict) else model
        row["version"] = agent.get("version")
    for rec in records:
        event = rec["event"]
        row = out[rec["agent"]]
        if event.get("type") == "span.model_request_end":
            row["model_requests"] += 1
        elif event.get("type") in ("agent.tool_use", "agent.custom_tool_use", "agent.mcp_tool_use"):
            row["tool_calls"] += 1
    return dict(out)
