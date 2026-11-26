import tomllib

import yaml

from scripts.build_environment import LOCK, OUTPUT, render, runtime_pins


def test_environment_matches_uv_lock() -> None:
    assert OUTPUT.read_text() == render(tomllib.loads(LOCK.read_text())), (
        "run: uv run python -m scripts.build_environment"
    )


def test_pins_cover_the_runtime_dependencies_only() -> None:
    pins = {p.split("==")[0].lower() for p in runtime_pins(tomllib.loads(LOCK.read_text()))}
    assert {"astropy", "astroquery", "batman-package", "transitleastsquares", "wotan"} <= pins
    assert not pins & {"anthropic", "pytest", "ruff", "pre-commit", "import-linter"}


def test_environment_shape() -> None:
    env = yaml.safe_load(OUTPUT.read_text())
    net = env["config"]["networking"]
    assert net["type"] == "limited"
    assert net["allow_package_managers"] is True
    assert "stpubdata.s3.us-east-1.amazonaws.com" in net["allowed_hosts"]
    assert all("==" in p for p in env["config"]["packages"]["pip"])
