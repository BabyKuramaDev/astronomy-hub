"""runtime/ with a fake platform: no network, no credits."""

import io
import json
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from runtime.audit import audit, check_command
from runtime.checks import acceptance, agent_names, setup_report
from runtime.ledger import SpendCapError, record, spent_cents
from runtime.managed import ManagedAgentsRuntime, RunConfig
from runtime.outputs import extract, validate
from runtime.platform import ManagedAgentsPlatform
from runtime.ports import Event, SessionSpec
from runtime.repo import RepoStateError, resource
from tests.contracts.conftest import envelope

TIC = 100100827


def dossier_tarball(final: str = "candidate", period: float = 0.9414) -> bytes:
    signal = {
        "detected": True,
        "period_days": period,
        "epoch_btjd": 1354.4578,
        "duration_hours": 2.2,
        "depth_ppm": 9500.0,
        "snr": 120.5,
        "n_transits": 25,
        "sectors": [2, 3],
        "method": "bls",
        "other_peaks": [],
    }
    decision = {"mode": "eval", "final": final, "reason": "rule", "next_step": "follow up"}
    files = {
        "signal.json": envelope(signal),
        "decision.json": envelope(
            decision, produced_by={"context": "direction", "tool": "decide", "version": "0.1.0"}
        ),
        "report.md": "# report\n",
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, payload in files.items():
            data = (payload if isinstance(payload, str) else json.dumps(payload)).encode()
            info = tarfile.TarInfo(f"{TIC}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def tool_use(eid: str, command: str, ask: bool = False) -> Event:
    return {
        "id": eid,
        "type": "agent.tool_use",
        "name": "bash",
        "input": {"command": command},
        "evaluated_permission": "ask" if ask else "allow",
    }


NAMES = agent_names()
DIRECTOR = "Astronomy Hub Director"


class FakePlatform:
    def __init__(self, streams: list[list[Event | Exception]], tarball: bytes | None) -> None:
        self.streams = streams
        self.tarball = tarball
        self.sent: list[tuple[str, Any]] = []
        self.created: list[SessionSpec] = []
        self.history: list[Event] = []

    def create_session(self, spec: SessionSpec) -> str:
        self.created.append(spec)
        return "sesn_test"

    @contextmanager
    def stream(self, session_id: str) -> Iterator[Iterator[Event]]:
        script = self.streams.pop(0)

        def gen() -> Iterator[Event]:
            for item in script:
                if isinstance(item, Exception):
                    raise item
                self.history.append(item)
                yield item

        yield gen()

    def send_message(self, session_id: str, text: str) -> None:
        self.sent.append(("message", text))

    def deny_tool(self, session_id: str, event_id: str, message: str) -> None:
        self.sent.append(("deny", event_id))

    def interrupt(self, session_id: str) -> None:
        self.sent.append(("interrupt", None))

    def list_events(self, session_id: str) -> list[Event]:
        return list(self.history)

    def session(self, session_id: str) -> dict[str, Any]:
        return {
            "status": "idle",
            "usage": {"list_cost": {"amount": "180", "currency": "USD"}, "active_seconds": 412.5},
        }

    def threads(self, session_id: str) -> list[dict[str, Any]]:
        out = [
            {
                "id": "sthr_main",
                "parent_thread_id": None,
                "agent": {"name": DIRECTOR, "model": {"id": "claude-opus-5-5"}, "version": 3},
                "usage": {"list_cost": {"amount": "60"}, "input_tokens": 1000, "output_tokens": 50},
            }
        ]
        for k, name in enumerate(n for n in NAMES if n != DIRECTOR):
            out.append(
                {
                    "id": f"sthr_{k}",
                    "parent_thread_id": "sthr_main",
                    "agent": {"name": name, "model": "claude-sonnet-5-5", "version": 1},
                    "usage": {"list_cost": {"amount": "20"}, "input_tokens": 500},
                }
            )
        return out

    def thread_events(self, session_id: str, thread_id: str) -> list[Event]:
        return [
            {"id": f"{thread_id}_e1", "type": "span.model_request_end"},
            tool_use(
                f"{thread_id}_t1", "cd /workspace/astronomy-hub && bin/hub detection fold --tic 1"
            ),
        ]

    def output_files(self, session_id: str) -> list[dict[str, Any]]:
        return [{"id": "file_1", "filename": f"dossier-{TIC}.tar.gz"}] if self.tarball else []

    def download(self, file_id: str) -> bytes:
        assert self.tarball is not None
        return self.tarball


def config(tmp_path: Path, **kw: Any) -> RunConfig:
    return RunConfig(
        agent_id="agent_1",
        agent_version=3,
        environment_id="env_1",
        repo_url="https://github.com/x/y",
        commit="abc123",
        runs_dir=tmp_path / "runs",
        ledger=tmp_path / "runs" / "ledger.jsonl",
        cap_cents=2000,
        sleep=lambda _: None,
        **kw,
    )


PRIMARY: list[Event | Exception] = [
    {"id": "e1", "type": "session.status_running"},
    {"id": "e1b", "type": "span.model_request_end"},
    tool_use("e2", "cd /workspace/astronomy-hub && bin/setup-sandbox"),
    {
        "id": "e2r",
        "type": "agent.tool_result",
        "tool_use_id": "e2",
        "content": [{"type": "text", "text": '{"python3": "3.11", "mode": "uv", "seconds": 48}'}],
    },
    tool_use("e3", "curl https://exoplanetarchive.ipac.caltech.edu/x"),
    tool_use("e4", "rm -rf workspace", ask=True),
    tool_use("e5", "bin/hub direction decide --tic 1 --mode eval --reason r"),
    tool_use("e6", "cat workspace/exoplanets/1/decision.json > /tmp/x"),
    {"id": "e7", "type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
]


def test_a_complete_run(tmp_path: Path) -> None:
    platform = FakePlatform([list(PRIMARY)], dossier_tarball())
    result = ManagedAgentsRuntime(platform, config(tmp_path)).run(TIC, "exoplanets", "eval", 500)
    assert result.stop_reason == "end_turn"
    assert result.list_cost_cents == 180
    assert platform.created[0].budget_cents == 500
    assert platform.created[0].commit == "abc123"
    assert ("deny", "e4") in platform.sent
    assert sum(1 for kind, _ in platform.sent if kind == "message") == 1
    summary = json.loads(result.summary_file.read_text())
    assert summary["validated"] == ["decision.json", "signal.json"]
    assert summary["validation_errors"] == {}
    assert summary["agents"][DIRECTOR]["list_cost_cents"] == 60
    assert summary["agents"][DIRECTOR]["model"] == "claude-opus-5-5"
    assert all(summary["agents"][n]["model_requests"] == 1 for n in NAMES if n != DIRECTOR)
    flags = summary["audit"]["flags"]
    assert [(f["event_id"], f["before_decide"]) for f in flags] == [
        ("e3", True),
        ("e4", True),
        ("e6", False),
    ]
    lines = (result.summary_file.parent / "events.jsonl").read_text().splitlines()
    assert len(lines) == len(PRIMARY) + 2 * (len(NAMES) - 1)
    assert spent_cents(tmp_path / "runs" / "ledger.jsonl") == 180
    records = [json.loads(x) for x in lines]
    assert setup_report(records) == {"python3": "3.11", "mode": "uv", "seconds": 48}


def test_acceptance_checks(tmp_path: Path) -> None:
    platform = FakePlatform([list(PRIMARY)], dossier_tarball())
    result = ManagedAgentsRuntime(platform, config(tmp_path)).run(TIC, "exoplanets", "eval", 500)
    summary = json.loads(result.summary_file.read_text())
    passed = acceptance(summary, result.dossier, 0.9414522, "candidate")
    assert passed["passed"], passed
    summary["agents"].pop("Astronomy Hub Writer")
    failed = acceptance(summary, result.dossier, 0.5, "candidate")
    assert failed["agents_missing"] == ["Astronomy Hub Writer"]
    assert not failed["period_within_1_percent"]
    assert not failed["passed"]


def test_reconnects_after_a_dropped_stream(tmp_path: Path) -> None:
    first: list[Event | Exception] = [PRIMARY[0], PRIMARY[1], ConnectionError("dropped")]
    platform = FakePlatform([first, list(PRIMARY)], dossier_tarball())
    result = ManagedAgentsRuntime(platform, config(tmp_path)).run(TIC, "exoplanets", "eval", 500)
    assert result.stop_reason == "end_turn"
    assert sum(1 for kind, _ in platform.sent if kind == "message") == 1
    lines = (result.summary_file.parent / "events.jsonl").read_text().splitlines()
    ids = [json.loads(x)["event"]["id"] for x in lines]
    assert len(ids) == len(set(ids)), "events are deduplicated by id"


def test_missing_outputs_are_reported(tmp_path: Path) -> None:
    platform = FakePlatform([list(PRIMARY)], None)
    result = ManagedAgentsRuntime(platform, config(tmp_path)).run(TIC, "exoplanets", "eval", 500)
    assert result.dossier is None
    summary = json.loads(result.summary_file.read_text())
    assert "not found" in summary["validation_errors"][f"dossier-{TIC}.tar.gz"]


def test_spend_cap_blocks_a_new_session(tmp_path: Path) -> None:
    ledger = tmp_path / "runs" / "ledger.jsonl"
    record(ledger, "r1", "s1", 1700, "hello")
    platform = FakePlatform([], None)
    with pytest.raises(SpendCapError, match="cap"):
        ManagedAgentsRuntime(platform, config(tmp_path)).run(TIC, "exoplanets", "eval", 500)
    assert platform.created == []


@pytest.mark.parametrize(
    ("command", "allowed"),
    [
        ("cd /workspace/astronomy-hub && bin/hub detection search-period --tic 1", True),
        ("/workspace/astronomy-hub/bin/hub vetting run-gates --tic 1 2>&1 | head -50", True),
        ("bin/setup-sandbox", True),
        ("ls workspace/exoplanets/1 && cat workspace/exoplanets/1/signal.json | jq .data", True),
        ("curl https://exofop.ipac.caltech.edu/tess/target.php?id=1", False),
        ("python3 -c 'print(1)'", False),
        ("cat a.json > b.json", False),
        ("echo x >> notes.txt", False),
        ("cat signal.json | tee copy.json", False),
        ("rm -rf workspace", False),
        # quotes, loops and harmless shell, as the agents wrote them in the first hello run
        (
            "bin/hub detection select-peak --tic 1 --peak p1 --reason 'SNR 1251 > floor 39; ok'",
            True,
        ),
        ("cd /x && jq 'del(.. | arrays? | select(length>20))' signal.json", True),
        ("cd /x && bin/hub direction package-dossier --tic 1; echo EXIT=$?", True),
        ("cd /x; for f in a.json b.json; do echo $f; head -c 400 $f; done", True),
        (
            "bin/hub review reproduce --tic 1 2>&1 | tail -5; grep -n 'valid\\|context' bin/hub",
            True,
        ),
        ("for f in a b; do rm $f; done", False),
        ("cat $(ls *.json)", False),
        ("bin/hub vetting run-gates --tic 1 > gates.txt", False),
        ("python3 - <<'EOF'", False),
    ],
)
def test_allowlist(command: str, allowed: bool) -> None:
    assert (check_command(command) is None) == allowed


def test_audit_marks_commands_before_decide() -> None:
    records = [{"agent": "a", "thread_id": "t", "event": e} for e in PRIMARY if isinstance(e, dict)]
    assert [f.event_id for f in audit(records) if f.before_decide] == ["e3", "e4"]


def test_extract_and_validate(tmp_path: Path) -> None:
    dossier = extract(dossier_tarball(), tmp_path)
    assert dossier == tmp_path / str(TIC)
    (dossier / "vetting.json").write_text("{}")
    ok, errors = validate(dossier)
    assert ok == ["decision.json", "signal.json"]
    assert list(errors) == ["vetting.json"]


def test_lockfile_resources(tmp_path: Path) -> None:
    lock = tmp_path / "claude-lock.json"
    with pytest.raises(RepoStateError, match="ant apply"):
        resource("./environment.yaml", lock)
    lock.write_text(
        json.dumps(
            {
                "resources": {
                    "./contexts/direction/agent.md": {"id": "agent_9", "version": 4},
                    "environment.yaml": {"id": "env_9"},
                }
            }
        )
    )
    assert resource("./contexts/direction/agent.md", lock).version == 4
    assert resource("./environment.yaml", lock).id == "env_9"
    with pytest.raises(RepoStateError, match="not in claude-lock"):
        resource("./runtime/probe/agent.md", lock)


def test_platform_adapter_builds_the_session_request() -> None:
    calls: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        calls.update(kwargs)
        return SimpleNamespace(id="sesn_1")

    client = SimpleNamespace(beta=SimpleNamespace(sessions=SimpleNamespace(create=create)))
    spec = SessionSpec("agent_1", 3, "env_1", "https://github.com/x/y", "deadbeef", 500, "t", {})
    assert ManagedAgentsPlatform(client).create_session(spec) == "sesn_1"  # type: ignore[arg-type]
    assert calls["budget"] == {
        "type": "limit",
        "max_list_cost": {"amount": "500", "currency": "USD"},
    }
    assert calls["agent"] == {"type": "agent", "id": "agent_1", "version": 3}
    (repo,) = calls["resources"]
    assert repo["checkout"] == {"type": "commit", "sha": "deadbeef"}
    assert "authorization_token" not in repo
