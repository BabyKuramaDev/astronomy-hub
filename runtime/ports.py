"""The runtime port: run one star on an agent platform and bring its dossier back."""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

# eval: blind, ends at decide; full: eval plus Librarian and Writer (smoke test of the
# six agents); explore: Catalog may stop the case early.
RunMode = Literal["explore", "eval", "full"]
Event = dict[str, Any]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    session_id: str
    dossier: Path | None  # the downloaded dossier, None when no output came back
    list_cost_cents: int
    active_seconds: float
    wall_seconds: float
    stop_reason: str
    summary_file: Path


class AgentRuntime(Protocol):
    def run(self, tic_id: int, mission: str, mode: RunMode, budget_cents: int) -> RunResult: ...


@dataclass(frozen=True)
class SessionSpec:
    agent_id: str
    agent_version: int | None
    environment_id: str
    repo_url: str
    commit: str
    budget_cents: int
    title: str
    metadata: dict[str, str]


class Platform(Protocol):
    """What the runtime needs from Managed Agents; every payload is a plain dict."""

    def create_session(self, spec: SessionSpec) -> str: ...

    def stream(self, session_id: str) -> AbstractContextManager[Iterator[Event]]: ...

    def send_message(self, session_id: str, text: str) -> None: ...

    def deny_tool(self, session_id: str, event_id: str, message: str) -> None: ...

    def interrupt(self, session_id: str) -> None: ...

    def list_events(self, session_id: str) -> list[Event]: ...

    def session(self, session_id: str) -> dict[str, Any]: ...

    def threads(self, session_id: str) -> list[dict[str, Any]]: ...

    def thread_events(self, session_id: str, thread_id: str) -> list[Event]: ...

    def output_files(self, session_id: str) -> list[dict[str, Any]]: ...

    def download(self, file_id: str) -> bytes: ...
