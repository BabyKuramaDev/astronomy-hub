"""Offline guard: tests without the `network` marker cannot reach the network.

In the pytest process, socket connections to non-local hosts raise. Tool
subprocesses inherit HTTP(S) proxies that point to a closed local port, so any
request they make fails instead of reaching MAST.
"""

import socket
from typing import Any

import pytest

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
DEAD_PROXY = "http://127.0.0.1:9"


class NetworkAccessError(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _offline(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("network"):
        return
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> Any:
        if self.family != socket.AF_UNIX:
            host = address[0] if isinstance(address, tuple) else address
            if host not in LOCAL_HOSTS:
                raise NetworkAccessError(f"network access in an offline test: {address!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(var, DEAD_PROXY)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
