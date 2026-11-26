import socket
import subprocess
import sys

import pytest


def test_offline_tests_cannot_open_sockets() -> None:
    with (
        pytest.raises(OSError, match="offline"),
        socket.create_connection(("mast.stsci.edu", 443), timeout=5),
    ):
        pass


def test_tool_subprocesses_cannot_reach_mast() -> None:
    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('https://mast.stsci.edu', timeout=5)\n"
        "except OSError:\n"
        "    raise SystemExit(7)\n"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 7
