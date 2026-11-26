import tomllib

import yaml

from scripts.build_environment import (
    EVAL_HOSTS,
    EVAL_OUTPUT,
    LOCK,
    NAME,
    OUTPUT,
    render,
    runtime_pins,
)


def test_environment_matches_uv_lock() -> None:
    lock = tomllib.loads(LOCK.read_text())
    assert OUTPUT.read_text() == render(lock), "run: uv run python -m scripts.build_environment"
    assert EVAL_OUTPUT.read_text() == render(lock, f"{NAME}-eval", EVAL_HOSTS)


def test_eval_environment_reaches_only_mast() -> None:
    env = yaml.safe_load(EVAL_OUTPUT.read_text())
    assert env["name"] == "astronomy-hub-eval"
    hosts = env["config"]["networking"]["allowed_hosts"]
    assert hosts == ["mast.stsci.edu", "stpubdata.s3.us-east-1.amazonaws.com"]


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
    assert env["config"]["packages"] == {"pip": []}, "python3 is 3.11: setup-sandbox uses uv"
    assert "#   astropy==" in OUTPUT.read_text()
