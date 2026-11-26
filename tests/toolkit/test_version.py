from pathlib import Path

from shared.toolkit.version import HUB_VERSION, describe_version, hub_version


def test_describe_version() -> None:
    assert describe_version(None, dirty=False) == HUB_VERSION
    assert describe_version("abc1234", dirty=False) == f"{HUB_VERSION}+gabc1234"
    assert describe_version("abc1234", dirty=True) == f"{HUB_VERSION}+gabc1234.dirty"


def test_version_outside_git_is_plain(tmp_path: Path) -> None:
    assert hub_version.__wrapped__(tmp_path) == HUB_VERSION


def test_version_in_repo_has_sha() -> None:
    assert hub_version().startswith(f"{HUB_VERSION}+g")
