"""Use case: select-peak. Records which peak the Searcher chose, or that there is none."""

from dataclasses import dataclass
from typing import Any

from contexts.detection.domain.selection import SelectionError, no_signal, signal_from_peak
from shared.contracts import SearchFile
from shared.mission import DetectionConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

SEARCH = "search.json"
SIGNAL = "signal.json"


@dataclass
class SelectPeak:
    dossier: Dossier
    meta: ToolMeta
    config: DetectionConfig

    def execute(self, peak_id: str | None) -> dict[str, Any]:
        search = self.dossier.read_envelope(SEARCH, SearchFile).data
        try:
            data = (
                no_signal(search)
                if peak_id is None
                else signal_from_peak(
                    search,
                    peak_id,
                    sde_min=self.config.sde_min,
                    min_transits=self.config.min_transits,
                )
            )
        except SelectionError as exc:
            raise InvalidInputError(str(exc)) from exc
        self.dossier.write_envelope(SIGNAL, self.meta.envelope(data, self.dossier.reads))
        summary: dict[str, Any] = {"tic_id": self.meta.tic_id, "detected": data.detected}
        if data.detected:
            summary |= {
                "peak": peak_id,
                "period_days": data.period_days,
                "epoch_btjd": data.epoch_btjd,
                "duration_hours": data.duration_hours,
                "depth_ppm": data.depth_ppm,
                "sde": data.sde,
                "snr": data.snr,
                "n_transits": data.n_transits,
            }
        summary |= {"n_other_peaks": len(data.other_peaks), "file": SIGNAL}
        return summary
