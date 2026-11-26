"""The MAST adapter retries transient errors and then reports data not available (exit 3)."""

import pytest
import requests

from contexts.acquisition.infrastructure.mast import MastLightcurveArchive
from shared.toolkit.errors import DataNotAvailableError
from shared.toolkit.retry import RetryPolicy


def test_transient_errors_are_retried_then_exit_3(monkeypatch: pytest.MonkeyPatch) -> None:
    from astroquery.mast import Observations

    calls = []

    def down(**_: object) -> None:
        calls.append(1)
        raise requests.ConnectionError("MAST is down")

    monkeypatch.setattr(Observations, "query_criteria", down)
    waits: list[float] = []
    archive = MastLightcurveArchive(RetryPolicy(4, 2.0, waits.append))
    with pytest.raises(DataNotAvailableError, match="observation query failed") as info:
        archive.available_sectors(1, "SPOC", 120.0)
    assert info.value.exit_code == 3
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
