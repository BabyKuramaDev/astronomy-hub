import argparse
import json
from pathlib import Path

import pytest

from shared.contracts import DecisionData, LogEntry
from shared.kernel.contexts import Context
from shared.toolkit.cli import ToolCli, ToolContext, ToolResult
from shared.toolkit.errors import DataNotAvailableError, InvalidInputError


def ok(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    data = DecisionData(mode="eval", final="no_signal", reason="r", next_step="n")
    ctx.dossier.write_envelope("decision.json", ctx.meta.envelope(data, ctx.dossier.reads))
    return ToolResult(summary={"final": "no_signal", "tic": ctx.tic_id}, reason=args.reason)


def invalid(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    raise InvalidInputError("bad peak\nsecond line")


def missing(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    raise DataNotAvailableError("no light curve")


def crash(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
    raise RuntimeError("boom")


@pytest.fixture
def cli() -> ToolCli:
    tools = ToolCli(Context.DIRECTION)
    tools.tool("ok", "writes a decision", ok).add_argument("--reason")
    tools.tool("invalid", "invalid input", invalid)
    tools.tool("missing", "data not available", missing)
    tools.tool("crash", "unexpected error", crash)
    return tools


def run(cli: ToolCli, tmp_path: Path, *args: str) -> int:
    return cli.main([*args, "--tic", "7", "--workspace", str(tmp_path)])


def log_lines(tmp_path: Path) -> list[LogEntry]:
    path = tmp_path / "exoplanets" / "7" / "log.jsonl"
    return [LogEntry.model_validate_json(line) for line in path.read_text().splitlines()]


def test_success_prints_summary_and_logs(
    cli: ToolCli, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(cli, tmp_path, "ok", "--reason", "because") == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {"final": "no_signal", "tic": 7}
    assert out.err == ""
    [entry] = log_lines(tmp_path)
    assert entry.exit_code == 0
    assert entry.reason == "because"
    assert entry.tool == "ok"
    assert set(entry.outputs) == {"decision.json"}
    assert entry.summary == {"final": "no_signal", "tic": 7}


@pytest.mark.parametrize(("tool", "code"), [("invalid", 2), ("missing", 3), ("crash", 1)])
def test_errors_map_to_exit_codes_and_one_line(
    cli: ToolCli, tmp_path: Path, capsys: pytest.CaptureFixture[str], tool: str, code: int
) -> None:
    assert run(cli, tmp_path, tool) == code
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.count("\n") == 1
    assert out.err.startswith("error: ")
    [entry] = log_lines(tmp_path)
    assert entry.exit_code == code
    assert entry.error


def test_argparse_errors_are_one_line_exit_2(
    cli: ToolCli, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["ok", "--tic", "-3"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "must be positive" in err


def test_unknown_mission_exits_2(
    cli: ToolCli, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(cli, tmp_path, "ok", "--mission", "astrology") == 2
    assert "unknown mission" in capsys.readouterr().err


def test_caches_stay_inside_the_dossier(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def probe(args: argparse.Namespace, ctx: ToolContext) -> ToolResult:
        import os

        from astropy.config import get_cache_dir

        seen["astropy"] = get_cache_dir()
        seen["mpl"] = os.environ["MPLCONFIGDIR"]
        return ToolResult(summary={})

    tools = ToolCli(Context.DETECTION)
    tools.tool("probe", "probe caches", probe)
    assert tools.main(["probe", "--tic", "7", "--workspace", str(tmp_path)]) == 0
    cache = tmp_path / "exoplanets" / "7" / ".cache"
    assert Path(seen["astropy"]).is_relative_to(cache)
    assert Path(seen["mpl"]) == tmp_path / ".cache" / "matplotlib"
