"""Allowlist audit of the agents' bash commands.

The sandbox is shared and every agent has bash, so in eval mode any agent could
reach an allowed host or write a file. A blocklist always falls short; instead
every bash command must be a repository tool (bin/hub, bin/setup-sandbox) or a
read-only inspection. Anything else is flagged in summary.json, with whether it
happened before decide.
"""

import re
import shlex
from dataclasses import asdict, dataclass
from typing import Any

TOOL_ENTRYPOINTS = ("bin/hub", "bin/setup-sandbox")
READ_ONLY = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "grep",
        "jq",
        "pwd",
        "cd",
        "file",
        "stat",
        "du",
        "sort",
        "uniq",
        "cut",
        "tree",
        "true",
        "date",
        "basename",
        "dirname",
        "realpath",
    }
)
SEPARATORS = re.compile(r"&&|\|\||;|\||\n")
REDIRECTION = re.compile(r"(?<![0-9&])>|>>|\btee\b")


@dataclass(frozen=True)
class Flag:
    agent: str
    thread_id: str
    event_id: str
    command: str
    reason: str
    before_decide: bool


def _is_tool(program: str) -> bool:
    return any(program == e or program.endswith("/" + e) for e in TOOL_ENTRYPOINTS)


def check_command(command: str) -> str | None:
    """None if every segment is a repository tool or a read-only inspection; else why not."""
    if REDIRECTION.search(command.replace("2>&1", "").replace("2>/dev/null", "")):
        return "writes through a redirection"
    for segment in SEPARATORS.split(command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            words = shlex.split(segment)
        except ValueError:
            return f"cannot parse: {segment!r}"
        while words and "=" in words[0] and not words[0].startswith("-"):
            words = words[1:]  # VAR=value prefixes
        if not words:
            continue
        program = words[0]
        if _is_tool(program):
            continue
        if program in READ_ONLY:
            continue
        return f"not a repository tool or a read-only command: {program}"
    return None


def audit(events: list[dict[str, Any]]) -> list[Flag]:
    """Flags for every bash call outside the allowlist; events carry agent and thread."""
    decided = False
    flags = []
    for record in events:
        event = record["event"]
        if event.get("type") == "agent.tool_use" and event.get("name") == "bash":
            command = str((event.get("input") or {}).get("command", ""))
            if "direction decide" in command:
                decided = True
            reason = check_command(command)
            if reason is not None:
                flags.append(
                    Flag(
                        record["agent"],
                        record["thread_id"],
                        str(event.get("id")),
                        command,
                        reason,
                        before_decide=not decided,
                    )
                )
    return flags


def as_dicts(flags: list[Flag]) -> list[dict[str, Any]]:
    return [asdict(f) for f in flags]
