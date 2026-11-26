"""Managed Agents through the Anthropic SDK. The only module that imports anthropic.

Credentials come from the environment (ANTHROPIC_API_KEY or an `ant auth login`
profile); nothing here reads, prints or stores a key.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import anthropic

from runtime.ports import Event, SessionSpec

MANAGED_AGENTS_BETA = "managed-agents-2026-04-01"


def _dump(obj: Any) -> dict[str, Any]:
    return obj.model_dump(mode="json") if hasattr(obj, "model_dump") else dict(obj)


class ManagedAgentsPlatform:
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()

    def create_session(self, spec: SessionSpec) -> str:
        agent: Any = (
            {"type": "agent", "id": spec.agent_id, "version": spec.agent_version}
            if spec.agent_version is not None
            else spec.agent_id
        )
        session = self.client.beta.sessions.create(
            agent=agent,
            environment_id=spec.environment_id,
            title=spec.title,
            metadata=spec.metadata,
            budget={
                "type": "limit",
                "max_list_cost": {"amount": str(spec.budget_cents), "currency": "USD"},
            },
            resources=[
                {
                    "type": "github_repository",
                    "url": spec.repo_url,
                    "checkout": {"type": "commit", "sha": spec.commit},
                }
            ],
        )
        return session.id

    @contextmanager
    def stream(self, session_id: str) -> Iterator[Iterator[Event]]:
        with self.client.beta.sessions.events.stream(session_id=session_id) as stream:
            yield (_dump(event) for event in stream)

    def _send(self, session_id: str, event: dict[str, Any]) -> None:
        self.client.beta.sessions.events.send(session_id=session_id, events=[event])

    def send_message(self, session_id: str, text: str) -> None:
        self._send(
            session_id, {"type": "user.message", "content": [{"type": "text", "text": text}]}
        )

    def deny_tool(self, session_id: str, event_id: str, message: str) -> None:
        self._send(
            session_id,
            {
                "type": "user.tool_confirmation",
                "tool_use_id": event_id,
                "result": "deny",
                "deny_message": message,
            },
        )

    def interrupt(self, session_id: str) -> None:
        self._send(session_id, {"type": "user.interrupt"})

    def list_events(self, session_id: str) -> list[Event]:
        return [_dump(e) for e in self.client.beta.sessions.events.list(session_id=session_id)]

    def session(self, session_id: str) -> dict[str, Any]:
        return _dump(self.client.beta.sessions.retrieve(session_id=session_id))

    def threads(self, session_id: str) -> list[dict[str, Any]]:
        return [_dump(t) for t in self.client.beta.sessions.threads.list(session_id=session_id)]

    def thread_events(self, session_id: str, thread_id: str) -> list[Event]:
        events = self.client.beta.sessions.threads.events.list(
            thread_id=thread_id, session_id=session_id
        )
        return [_dump(e) for e in events]

    def output_files(self, session_id: str) -> list[dict[str, Any]]:
        files = self.client.beta.files.list(scope_id=session_id, betas=[MANAGED_AGENTS_BETA])
        return [_dump(f) for f in files]

    def download(self, file_id: str) -> bytes:
        return self.client.beta.files.download(file_id=file_id).read()
