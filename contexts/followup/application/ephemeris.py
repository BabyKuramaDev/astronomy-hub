"""Use case: ephemeris."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from contexts.followup.domain.ephemeris import next_transits
from shared.contracts import EphemerisData, ModelFile, PredictedTransit
from shared.mission import FollowupConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

MODEL = "model.json"
EPHEMERIS = "ephemeris.json"


@dataclass
class Ephemeris:
    dossier: Dossier
    meta: ToolMeta
    config: FollowupConfig

    def execute(self, start: datetime) -> dict[str, Any]:
        if start.utcoffset() is None:
            raise InvalidInputError("--start must carry a time zone (use Z for UTC)")
        model = self.dossier.read_envelope(MODEL, ModelFile).data
        if model.status == "failed" or None in (
            model.period_days,
            model.epoch_btjd,
            model.duration_hours,
        ):
            raise InvalidInputError(f"model.json is a failed fit ({model.failure}): no ephemeris")
        period, epoch = model.period_days, model.epoch_btjd
        if period.value <= 0:
            raise InvalidInputError("model.json has a non-positive period")
        transits = next_transits(
            epoch=epoch.value,
            epoch_err=max(epoch.err_lower, epoch.err_upper),
            period=period.value,
            period_err=max(period.err_lower, period.err_upper),
            duration_hours=model.duration_hours.value,
            start=start,
            horizon_days=self.config.horizon_days,
            max_transits=self.config.max_transits,
        )
        data = EphemerisData(
            model_method=model.method,
            period_days=period,
            epoch_btjd=epoch,
            duration_hours=model.duration_hours.value,
            start_utc=start,
            horizon_days=self.config.horizon_days,
            transits=[PredictedTransit(**t.__dict__) for t in transits],
        )
        self.dossier.write_envelope(EPHEMERIS, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "model_method": model.method,
            "start_utc": start.isoformat().replace("+00:00", "Z"),
            "columns": ["n", "mid_utc", "err_minutes"],
            "transits": [
                [t.n, t.mid_utc.isoformat().replace("+00:00", "Z"), round(t.err_minutes, 2)]
                for t in transits
            ],
            "note": "times are barycentric (BJD_TDB) shown in UTC; up to ~8 min from local",
            "file": EPHEMERIS,
        }
