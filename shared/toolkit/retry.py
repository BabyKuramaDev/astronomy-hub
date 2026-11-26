"""Retry transient errors of remote services (MAST, NASA Exoplanet Archive, ExoFOP).

Only errors that may go away by themselves are retried: connection failures,
timeouts and HTTP 5xx. Anything else (a 4xx, a malformed answer, no data) fails
at once. Waits grow exponentially: backoff_s, 2 * backoff_s, 4 * backoff_s...
"""

import socket
import time
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass, field


def _status_code(exc: BaseException) -> int | None:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def is_transient(exc: BaseException) -> bool:
    code = _status_code(exc)
    if code is not None:
        return code >= 500
    try:
        import requests
    except ImportError:  # pragma: no cover - requests comes with astroquery
        requests = None  # type: ignore[assignment]
    if requests is not None and isinstance(
        exc, requests.ConnectionError | requests.Timeout | requests.exceptions.ChunkedEncodingError
    ):
        return True
    if isinstance(exc, urllib.error.URLError):
        return True
    return isinstance(exc, TimeoutError | socket.timeout | ConnectionError)


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1
    backoff_s: float = 0.0
    sleep: Callable[[float], None] = field(default=time.sleep, compare=False)

    def call[T](self, action: Callable[[], T]) -> T:
        """Run action; retry transient errors, re-raise the last one when attempts run out."""
        for attempt in range(self.attempts):
            try:
                return action()
            except Exception as exc:
                if attempt + 1 >= self.attempts or not is_transient(exc):
                    raise
                self.sleep(self.backoff_s * 2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover
