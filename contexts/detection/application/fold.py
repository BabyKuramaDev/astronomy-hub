"""Use case: fold."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from contexts.detection.domain.fold import FoldResult, fold
from shared.contracts import FoldBin, FoldData, OddEven, SearchFile
from shared.mission import FoldConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

CLEAN = "lightcurve_clean.parquet"
SEARCH = "search.json"

FigureRenderer = Callable[[FoldResult, str], bytes]


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


@dataclass(frozen=True)
class FoldRequest:
    peak_id: str | None = None
    period_days: float | None = None
    epoch_btjd: float | None = None
    duration_hours: float | None = None


@dataclass
class Fold:
    dossier: Dossier
    meta: ToolMeta
    config: FoldConfig
    render: FigureRenderer

    def _ephemeris(self, req: FoldRequest, time: np.ndarray) -> tuple[float, float, float]:
        if req.peak_id is not None:
            search = self.dossier.read_envelope(SEARCH, SearchFile).data
            peak = search.peak(req.peak_id)
            if peak is None:
                raise InvalidInputError(f"unknown peak {req.peak_id!r} in search.json")
            return (
                req.period_days or peak.period_days,
                req.epoch_btjd if req.epoch_btjd is not None else peak.epoch_btjd,
                req.duration_hours or peak.duration_hours,
            )
        if req.period_days is None or req.duration_hours is None:
            raise InvalidInputError("give --peak, or --period and --duration")
        if req.period_days <= 0 or req.duration_hours <= 0:
            raise InvalidInputError("period and duration must be positive")
        epoch = req.epoch_btjd if req.epoch_btjd is not None else float(time.min())
        return req.period_days, epoch, req.duration_hours

    def execute(self, req: FoldRequest) -> dict[str, Any]:
        table = self.dossier.read_table(CLEAN)
        period, epoch, duration = self._ephemeris(req, table["time_btjd"])
        if duration / 24.0 >= period:
            raise InvalidInputError("duration must be shorter than the period")
        result = fold(
            table["time_btjd"],
            table["flux"],
            period_days=period,
            epoch_btjd=epoch,
            duration_hours=duration,
            window_durations=self.config.window_durations,
            n_bins=self.config.n_bins,
        )
        tag = f"P{period:.6f}"
        data_rel, figure_rel, json_rel = (
            f"folds/{tag}.parquet",
            f"figures/fold_{tag}.png",
            f"folds/{tag}.json",
        )
        self.dossier.write_table(
            data_rel,
            {
                "phase_hours": result.phase_hours,
                "flux": result.flux,
                "epoch_index": result.epoch_index,
            },
        )
        title = f"TIC {self.meta.tic_id}  P = {period:.6f} d"
        self.dossier.write_bytes(figure_rel, self.render(result, title))
        diff, sigma = result.odd_even_difference
        data = FoldData(
            source="peak" if req.peak_id else "manual",
            peak_id=req.peak_id,
            period_days=period,
            epoch_btjd=epoch,
            duration_hours=duration,
            n_points=result.n_points,
            n_transits_covered=result.n_transits_covered,
            in_transit_depth_ppm=result.in_transit.value_ppm,
            oot_scatter_ppm=result.oot_scatter_ppm,
            bins=[FoldBin(**b.__dict__) for b in result.bins],
            odd_even=OddEven(
                depth_odd_ppm=result.odd.value_ppm,
                depth_odd_err_ppm=result.odd.err_ppm,
                depth_even_ppm=result.even.value_ppm,
                depth_even_err_ppm=result.even.err_ppm,
                difference_ppm=diff,
                difference_sigma=sigma,
                n_odd=result.odd.n_points,
                n_even=result.even.n_points,
            ),
            data_file=data_rel,
            figure_file=figure_rel,
        )
        self.dossier.write_envelope(json_rel, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "peak": req.peak_id,
            "period_days": round(period, 6),
            "epoch_btjd": round(epoch, 5),
            "duration_hours": round(duration, 3),
            "n_transits_covered": result.n_transits_covered,
            "depth_ppm": _round(result.in_transit.value_ppm),
            "depth_err_ppm": _round(result.in_transit.err_ppm),
            "oot_scatter_ppm": _round(result.oot_scatter_ppm),
            "odd_even": {
                "odd_ppm": _round(result.odd.value_ppm),
                "even_ppm": _round(result.even.value_ppm),
                "difference_ppm": _round(diff),
                "difference_sigma": _round(sigma, 2),
            },
            "bins": {
                "columns": ["phase_hours", "depth_ppm", "n_points"],
                "rows": [
                    [round(b.phase_hours, 2), _round(b.depth_ppm), b.n_points] for b in result.bins
                ],
            },
            "files": [json_rel, data_rel, figure_rel],
        }
