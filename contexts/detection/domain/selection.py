"""select-peak: turn the Searcher's choice into signal.json data."""

from shared.contracts import Peak, PeriodSearchData, SignalData


class SelectionError(ValueError):
    """The requested peak cannot be recorded as a signal."""


def _others(search: PeriodSearchData, chosen: str | None) -> list[Peak]:
    return [
        Peak(period_days=p.period_days, snr=p.snr, depth_ppm=p.depth_ppm)
        for p in search.peaks
        if p.id != chosen
    ]


def signal_from_peak(
    search: PeriodSearchData, peak_id: str, *, snr_min: float, min_transits: int
) -> SignalData:
    peak = search.peak(peak_id)
    if peak is None:
        known = ", ".join(p.id for p in search.peaks) or "none"
        raise SelectionError(f"unknown peak {peak_id!r} (peaks in search.json: {known})")
    if peak.snr < snr_min:
        raise SelectionError(f"{peak_id} has SNR {peak.snr:.2f}, below snr_min {snr_min:g}")
    if peak.n_transits < min_transits:
        raise SelectionError(
            f"{peak_id} has {peak.n_transits} transits, below min_transits {min_transits}"
        )
    return SignalData(
        detected=True,
        period_days=peak.period_days,
        epoch_btjd=peak.epoch_btjd,
        duration_hours=peak.duration_hours,
        depth_ppm=peak.depth_ppm,
        snr=peak.snr,
        n_transits=peak.n_transits,
        sectors=search.sectors,
        method=search.method,
        other_peaks=_others(search, peak_id),
    )


def no_signal(search: PeriodSearchData) -> SignalData:
    return SignalData(
        detected=False,
        sectors=search.sectors,
        method=search.method,
        other_peaks=_others(search, None),
    )
