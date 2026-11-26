import urllib.error

import pytest
import requests

from shared.toolkit.retry import RetryPolicy, is_transient


class Flaky:
    def __init__(self, errors: list[Exception]) -> None:
        self.errors = errors
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def _http(code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = code
    return requests.HTTPError(f"{code}", response=response)


@pytest.mark.parametrize(
    ("exc", "transient"),
    [
        (requests.ConnectionError("reset"), True),
        (requests.Timeout("slow"), True),
        (TimeoutError(), True),
        (urllib.error.URLError("no route"), True),
        (urllib.error.HTTPError("u", 503, "down", None, None), True),
        (urllib.error.HTTPError("u", 404, "missing", None, None), False),
        (_http(502), True),
        (_http(400), False),
        (ValueError("bad table"), False),
    ],
)
def test_is_transient(exc: Exception, transient: bool) -> None:
    assert is_transient(exc) is transient


def test_retries_with_exponential_backoff() -> None:
    waits: list[float] = []
    action = Flaky([requests.ConnectionError("a"), _http(503)])
    assert RetryPolicy(4, 2.0, waits.append).call(action) == "ok"
    assert action.calls == 3
    assert waits == [2.0, 4.0]


def test_gives_up_after_the_last_attempt() -> None:
    waits: list[float] = []
    action = Flaky([TimeoutError()] * 5)
    with pytest.raises(TimeoutError):
        RetryPolicy(3, 1.0, waits.append).call(action)
    assert action.calls == 3
    assert waits == [1.0, 2.0]


def test_permanent_errors_are_not_retried() -> None:
    action = Flaky([_http(404)])
    with pytest.raises(requests.HTTPError):
        RetryPolicy(4, 1.0, lambda _: None).call(action)
    assert action.calls == 1
