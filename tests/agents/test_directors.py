"""The two Director agents come from one source and differ only in roster and steps."""

import re
from pathlib import Path

import yaml

from scripts.build_directors import DIRECTION, render_all

MAIN, EVAL = DIRECTION / "agent.md", DIRECTION / "agent_eval.md"
STEP = re.compile(r"^\d+\. ", re.M)
ROSTER_LINE = re.compile(r"^      - \.\./\w+/agent\.md\n", re.M)


def split(path: Path) -> tuple[dict, str]:
    _, front, body = path.read_text().split("---\n", 2)
    return yaml.safe_load(front), body


def test_files_match_the_source() -> None:
    for path, text in render_all().items():
        assert path.read_text() == text, "run: uv run python -m scripts.build_directors"


def without_roster_and_steps(path: Path) -> str:
    text = ROSTER_LINE.sub("", path.read_text())
    lines = text.splitlines(keepends=True)
    return "".join(line for line in lines if not STEP.match(line))


def test_directors_differ_only_in_roster_and_steps() -> None:
    assert without_roster_and_steps(MAIN) == without_roster_and_steps(EVAL)
    assert MAIN.read_text() != EVAL.read_text()


def roster_names(path: Path) -> set[str]:
    front, _ = split(path)
    return {
        split(DIRECTION / r)[0]["name"]
        for r in front["multiagent"]["subagents"]["predefined_agents"]
    }


def named_agents(path: Path) -> set[str]:
    _, body = split(path)
    steps = "".join(line for line in body.splitlines(keepends=True) if STEP.match(line))
    return set(
        re.findall(r"Astronomy Hub (?:Searcher|Librarian|Devil's Advocate|Reviewer|Writer)", steps)
    )


def test_steps_call_exactly_the_roster() -> None:
    assert named_agents(MAIN) == roster_names(MAIN)
    assert (
        named_agents(EVAL)
        == roster_names(EVAL)
        == {"Astronomy Hub Searcher", "Astronomy Hub Devil's Advocate", "Astronomy Hub Reviewer"}
    )


def test_eval_director_ends_at_decide() -> None:
    _, body = split(EVAL)
    steps = [line for line in body.splitlines() if STEP.match(line)]
    assert "direction decide --tic <TIC> --mode eval" in steps[-2]
    assert "package-dossier" in steps[-1]
    for absent in ("mcmc", "Librarian", "Writer"):
        assert absent not in body
