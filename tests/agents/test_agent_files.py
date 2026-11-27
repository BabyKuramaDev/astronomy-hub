"""The agent definitions synced with ant apply: shape, prompts and roster."""

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
COMMON = (REPO / "shared" / "prompts" / "common.md").read_text().strip()
AGENTS = {
    "direction": "claude-opus-5-5",
    "detection": "claude-sonnet-5-5",
    "catalog": "claude-sonnet-5-5",
    "vetting": "claude-opus-5-5",
    "review": "claude-opus-5-5",
    "reporting": "claude-sonnet-5-5",
}
WEB_TOOLS = {"web_search", "web_fetch"}


def load(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text()
    assert text.startswith("---\n")
    _, front, body = text.split("---\n", 2)
    return yaml.safe_load(front), body


def enabled_tools(front: dict[str, Any]) -> set[str]:
    (toolset,) = front["tools"]
    assert toolset["type"] == "agent_toolset_20260401"
    assert toolset["default_config"] == {
        "enabled": False,
        "permission_policy": {"type": "always_allow"},
    }
    return {c["name"] for c in toolset["configs"] if c.get("enabled")}


@pytest.mark.parametrize(("context", "model"), AGENTS.items())
def test_agent_file(context: str, model: str) -> None:
    path = REPO / "contexts" / context / "agent.md"
    front, body = load(path)
    assert front["model"] == model
    assert front["name"].startswith("Astronomy Hub ")
    assert COMMON in body, "every prompt carries the common rules word for word"
    tools = enabled_tools(front)
    assert {"bash", "read", "glob", "grep"} <= tools
    assert not tools & {"write", "edit"}, "agents never edit dossier files by hand"
    assert bool(tools & WEB_TOOLS) == (context == "catalog"), "only the Librarian has the web"
    assert "./skill" in front["skills"]
    for ref in front["skills"]:
        assert (path.parent / ref / "SKILL.md").is_file(), ref


def test_web_domains_are_within_the_environment() -> None:
    front, _ = load(REPO / "contexts" / "catalog" / "agent.md")
    env = yaml.safe_load((REPO / "environment.yaml").read_text())
    hosts = set(env["config"]["networking"]["allowed_hosts"])
    for config in front["tools"][0]["configs"]:
        if config["name"] in WEB_TOOLS:
            assert set(config["allowed_domains"]) <= hosts


def test_director_roster() -> None:
    front, body = load(REPO / "contexts" / "direction" / "agent.md")
    multi = front["multiagent"]
    assert multi["type"] == "multiagent_20261001"
    assert multi["workflows"] == {"type": "disabled"}
    assert multi["subagents"]["inline_agents"] == {"type": "disabled"}
    roster = multi["subagents"]["predefined_agents"]
    assert sorted(roster) == sorted(f"../{c}/agent.md" for c in AGENTS if c != "direction")
    names = {load(REPO / "contexts" / "direction" / r)[0]["name"] for r in roster}
    for name in names:
        assert name in body, f"the Director's prompt names {name}"
    for context in AGENTS:
        if context != "direction":
            assert "multiagent" not in load(REPO / "contexts" / context / "agent.md")[0]


def test_mode_orders_in_the_director_prompt() -> None:
    _, body = load(REPO / "contexts" / "direction" / "agent.md")
    decide = body.index("direction decide")
    assert decide < body.index("Full mode only: delegate to Astronomy Hub Librarian now")
    assert body.index("Full mode only: delegate") < body.index("Delegate to Astronomy Hub Writer")
    assert body.index("Astronomy Hub Writer.") < body.index("package-dossier")
    assert "Never in full mode" in body


def test_skills_are_one_per_context_and_named_uniquely() -> None:
    names = []
    for skill in sorted((REPO / "contexts").glob("*/skill/SKILL.md")):
        front, _ = load(skill)
        assert front["name"] == f"hub-{skill.parent.parent.name}"
        assert front["description"]
        names.append(front["name"])
    assert len(names) == 10
    assert not (REPO / ".claude" / "skills").exists()


def test_skills_open_with_the_exact_commands() -> None:
    from scripts.list_tools import tools

    for context, rows in tools().items():
        text = (REPO / "contexts" / context / "skill" / "SKILL.md").read_text()
        commands = text[text.index("## Commands") : text.index("## Tools")]
        for name, _help, usage in rows:
            assert usage in commands, f"{context} skill lacks the exact syntax of {name}"
            assert f"bin/hub {context} {name} --tic 123456789" in commands, f"no example for {name}"
