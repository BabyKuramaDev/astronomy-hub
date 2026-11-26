import pytest

from contexts.detection.domain.selection import SelectionError, no_signal, signal_from_peak
from shared.contracts import PeriodSearchData, SearchPeak


def peak(n: int, snr: float = 20.0, n_transits: int = 10) -> SearchPeak:
    return SearchPeak(
        id=f"p{n}",
        period_days=float(n),
        epoch_btjd=1000.0,
        duration_hours=2.0,
        depth_ppm=1000.0,
        snr=snr,
        n_transits=n_transits,
        power=10.0,
    )


SEARCH = PeriodSearchData(
    method="bls",
    sectors=[2, 3],
    period_min_days=0.5,
    period_max_days=15.0,
    durations_hours=[2.0],
    bin_minutes=10.0,
    n_periods=100,
    peaks=[peak(1), peak(2, snr=5.0), peak(3, n_transits=2)],
    discarded=[],
)


def test_signal_from_peak_keeps_others() -> None:
    signal = signal_from_peak(SEARCH, "p1", snr_min=8.0, min_transits=3)
    assert signal.detected
    assert signal.period_days == 1.0
    assert [p.period_days for p in signal.other_peaks] == [2.0, 3.0]
    assert signal.sectors == [2, 3]


@pytest.mark.parametrize(
    ("peak_id", "message"),
    [("p9", "unknown peak"), ("p2", "snr_min"), ("p3", "min_transits")],
)
def test_peak_must_clear_mission_thresholds(peak_id: str, message: str) -> None:
    with pytest.raises(SelectionError, match=message):
        signal_from_peak(SEARCH, peak_id, snr_min=8.0, min_transits=3)


def test_no_signal_lists_every_peak() -> None:
    signal = no_signal(SEARCH)
    assert not signal.detected
    assert signal.period_days is None
    assert len(signal.other_peaks) == 3
