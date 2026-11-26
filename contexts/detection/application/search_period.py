"""Use case: search-period."""

from dataclasses import dataclass
from typing import Any

import numpy as np

from contexts.detection.domain.bls import SearchError, SearchParams, search_periods
from shared.contracts import DiscardedPeak, PeriodSearchData, SearchPeak
from shared.mission import DetectionConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import DataNotAvailableError
from shared.toolkit.meta import ToolMeta

CLEAN = "lightcurve_clean.parquet"
SEARCH = "search.json"
METHOD = "bls"


def params_from(config: DetectionConfig) -> SearchParams:
    return SearchParams(
        period_min_days=config.period_min_days,
        period_max_days=config.period_max_days,
        durations_hours=tuple(config.durations_hours),
        bin_minutes=config.bin_minutes,
        frequency_factor=config.frequency_factor,
        n_peaks=config.n_peaks,
        examine_factor=config.examine_factor,
        peak_separation=config.peak_separation,
        harmonic_max_integer=config.harmonic_max_integer,
        harmonic_tolerance=config.harmonic_tolerance,
        min_transits=config.min_transits,
    )


@dataclass
class SearchPeriod:
    dossier: Dossier
    meta: ToolMeta
    config: DetectionConfig

    def execute(self) -> dict[str, Any]:
        table = self.dossier.read_table(CLEAN)
        try:
            outcome = search_periods(
                table["time_btjd"], table["flux"], table["flux_err"], params_from(self.config)
            )
        except SearchError as exc:
            raise DataNotAvailableError(str(exc)) from exc
        peaks = [
            SearchPeak(
                id=f"p{k}",
                period_days=c.period_days,
                epoch_btjd=c.epoch_btjd,
                duration_hours=c.duration_hours,
                depth_ppm=c.depth_ppm,
                snr=max(c.snr, 0.0),
                n_transits=max(c.n_transits, 1),
                power=c.power,
            )
            for k, c in enumerate(outcome.peaks, start=1)
        ]
        discarded = [
            DiscardedPeak(
                period_days=d.candidate.period_days,
                epoch_btjd=d.candidate.epoch_btjd,
                duration_hours=d.candidate.duration_hours,
                depth_ppm=d.candidate.depth_ppm,
                snr=d.candidate.snr,
                power=d.candidate.power,
                reason=d.reason,  # type: ignore[arg-type]
                harmonic_of=f"p{d.harmonic_of + 1}" if d.harmonic_of is not None else None,
                ratio=f"{d.ratio.numerator}/{d.ratio.denominator}" if d.ratio else None,
            )
            for d in outcome.discarded
        ]
        data = PeriodSearchData(
            method=METHOD,
            sectors=sorted({int(s) for s in np.unique(table["sector"])}),
            period_min_days=outcome.period_min_days,
            period_max_days=outcome.period_max_days,
            durations_hours=list(outcome.durations_hours),
            bin_minutes=self.config.bin_minutes,
            n_periods=outcome.n_periods,
            peaks=peaks,
            discarded=discarded,
        )
        self.dossier.write_envelope(SEARCH, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "n_periods": outcome.n_periods,
            "period_range_days": [data.period_min_days, round(data.period_max_days, 4)],
            "snr_min": self.config.snr_min,
            "min_transits": self.config.min_transits,
            "peaks": [
                {
                    "id": p.id,
                    "period_days": round(p.period_days, 6),
                    "duration_hours": round(p.duration_hours, 2),
                    "depth_ppm": round(p.depth_ppm, 1),
                    "snr": round(p.snr, 2),
                    "n_transits": p.n_transits,
                }
                for p in peaks
            ],
            "discarded": [
                {
                    "period_days": round(d.period_days, 6),
                    "reason": d.reason,
                    **({"harmonic_of": d.harmonic_of, "ratio": d.ratio} if d.harmonic_of else {}),
                }
                for d in discarded
            ],
            "file": SEARCH,
        }
