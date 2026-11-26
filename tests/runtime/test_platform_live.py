"""Read-only checks against Claude Managed Agents: the synced resources exist.

Run with `make test-platform`. Excluded from `make test` and CI. Creates no session.
"""

import pytest

from runtime.repo import resource

pytestmark = pytest.mark.platform

FILES = [
    "./contexts/direction/agent.md",
    "./contexts/detection/agent.md",
    "./contexts/catalog/agent.md",
    "./contexts/vetting/agent.md",
    "./contexts/review/agent.md",
    "./contexts/reporting/agent.md",
]


@pytest.mark.parametrize("path", FILES)
def test_agent_is_synced(path: str) -> None:
    import anthropic

    ref = resource(path)
    agent = anthropic.Anthropic().beta.agents.retrieve(agent_id=ref.id)
    assert agent.version == ref.version


def test_environment_is_synced() -> None:
    import anthropic

    env = anthropic.Anthropic().beta.environments.retrieve(
        environment_id=resource("./environment.yaml").id
    )
    assert env.config.networking.type == "limited"
