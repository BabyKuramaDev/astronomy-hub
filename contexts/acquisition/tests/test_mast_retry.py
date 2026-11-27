"""The MAST adapter retries transient errors and then reports data not available (exit 3)."""

import pytest
import requests

from contexts.acquisition.infrastructure.mast import MastLightcurveArchive
from shared.toolkit.errors import ServiceUnavailableError
from shared.toolkit.retry import RetryPolicy


def test_transient_errors_are_retried_then_mast_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from astroquery.mast import Observations

    calls = []

    def down(**_: object) -> None:
        calls.append(1)
        raise requests.ConnectionError("MAST is down")

    monkeypatch.setattr(Observations, "query_criteria", down)
    waits: list[float] = []
    archive = MastLightcurveArchive(RetryPolicy(4, 2.0, waits.append))
    with pytest.raises(
        ServiceUnavailableError, match="MAST unavailable: observation query"
    ) as info:
        archive.available_sectors(1, "SPOC", 120.0)
    assert info.value.exit_code == 1  # transient: rerun, not "no data" (exit 3)
    assert len(calls) == 4
    assert waits == [2.0, 4.0, 8.0]


def test_recovers_after_a_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from astroquery.mast import Observations

    answers: list[object] = [requests.Timeout("slow"), []]

    def flaky(**_: object) -> object:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(Observations, "query_criteria", flaky)
    archive = MastLightcurveArchive(RetryPolicy(3, 1.0, lambda _: None))
    assert archive.available_sectors(1, "SPOC", 120.0) == []


def test_remote_service_error_is_transient() -> None:
    from shared.toolkit.retry import is_transient

    class RemoteServiceError(Exception):  # astroquery's name for a failed MAST request
        pass

    assert is_transient(RemoteServiceError("Request failed"))


def test_the_deadline_stops_retries_before_the_bash_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from astroquery.mast import Observations, conf

    now = [0.0]

    def hang(**_: object) -> None:
        now[0] += min(100.0, float(conf.timeout))  # hangs until astroquery's timeout cuts it
        raise requests.Timeout("no answer")

    monkeypatch.setattr(Observations, "query_criteria", hang)
    policy = RetryPolicy(
        10,
        2.0,
        lambda w: now.__setitem__(0, now[0] + w),
        deadline_s=240.0,
        request_timeout_s=60.0,
        clock=lambda: now[0],
    )
    with pytest.raises(ServiceUnavailableError, match="MAST unavailable"):
        MastLightcurveArchive(policy).available_sectors(1, "SPOC", 120.0)
    assert now[0] <= 240.0 + 1.0, "the tool returns before the sandbox's 295 s limit"
