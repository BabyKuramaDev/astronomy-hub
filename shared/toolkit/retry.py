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
    if type(exc).__name__ == "RemoteServiceError":  # astroquery: the service failed
        return True
    return isinstance(exc, TimeoutError | socket.timeout | ConnectionError)


class DeadlineExceededError(TimeoutError):
    """The policy's total time ran out before the remote service answered."""


@dataclass(frozen=True)
class RetryPolicy:
    """attempts and exponential backoff; optionally a total deadline_s for every call made
    through this policy (counted from the first one), so a tool returns before a caller's
    own limit, and a per-request timeout for the caller to apply."""

    attempts: int = 1
    backoff_s: float = 0.0
    sleep: Callable[[float], None] = field(default=time.sleep, compare=False)
    deadline_s: float | None = None
    request_timeout_s: float | None = None
    clock: Callable[[], float] = field(default=time.monotonic, compare=False)
    _start: list[float] = field(default_factory=list, compare=False, repr=False)

    def remaining_s(self) -> float | None:
        if self.deadline_s is None:
            return None
        if not self._start:
            self._start.append(self.clock())
        return self.deadline_s - (self.clock() - self._start[0])

    def timeout_s(self) -> float | None:
        """The per-request timeout, never beyond what is left of the deadline."""
        left = self.remaining_s()
        if left is None:
            return self.request_timeout_s
        if self.request_timeout_s is None:
            return max(left, 1.0)
        return max(min(self.request_timeout_s, left), 1.0)

    def call[T](self, action: Callable[[], T]) -> T:
        """Run action; retry transient errors, re-raise the last one when attempts run out
        or when the next wait would go past the deadline."""
        for attempt in range(self.attempts):
            left = self.remaining_s()
            if left is not None and left <= 0:
                raise DeadlineExceededError(f"no answer within {self.deadline_s:g} s")
            try:
                return action()
            except Exception as exc:
                if attempt + 1 >= self.attempts or not is_transient(exc):
                    raise
                wait = self.backoff_s * 2**attempt
                left = self.remaining_s()
                if left is not None and left <= wait:
                    raise
                self.sleep(wait)
        raise AssertionError("unreachable")  # pragma: no cover
