"""Use case: conclude (review). The verdict comes from the rule; the agent gives the rationale."""

from dataclasses import dataclass
from typing import Any

from contexts.review.application.reproduce import REPRODUCTION
from contexts.review.domain.comparison import Tolerances, compare
from shared.contracts import ReproductionFile, ReviewData, SignalFile
from shared.mission import ReviewConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

SIGNAL = "signal.json"
REVIEW = "review.json"


@dataclass
class Conclude:
    dossier: Dossier
    meta: ToolMeta
    config: ReviewConfig

    def execute(self, rationale: str) -> dict[str, Any]:
        if not rationale.strip():
            raise InvalidInputError("--rationale must not be empty")
        if not self.dossier.exists(REPRODUCTION):
            raise InvalidInputError(f"{REPRODUCTION} not found: run reproduce first")
        repro = self.dossier.read_envelope(REPRODUCTION, ReproductionFile).data
        signal = self.dossier.read_envelope(SIGNAL, SignalFile).data
        if not signal.detected:
            raise InvalidInputError("signal.json has detected=false: there is nothing to compare")
        cfg = self.config
        # Like with like: the box depth on the Reviewer's own curve, never TLS's model depth.
        box = repro.box_depth_ppm
        result = compare(
            repro.detected,
            repro.period_days,
            box,
            repro.sde,
            repro.sde_min,
            signal.period_days,  # type: ignore[arg-type]
            signal.depth_ppm,  # type: ignore[arg-type]
            Tolerances(
                cfg.period_tolerance,
                cfg.depth_tolerance,
                cfg.alias_max_integer,
                cfg.epoch_tolerance_durations,
            ),
            epoch=repro.epoch_btjd,
            signal_epoch=signal.epoch_btjd,
            signal_duration_hours=signal.duration_hours,
        )
        depth = box if box is not None and box > 0 else None
        data = ReviewData(
            period_days_independent=repro.period_days,
            depth_ppm_independent=depth,
            disagreements=list(result.disagreements),
            verdict=result.verdict,  # type: ignore[arg-type]
            period_ratio=result.period_ratio,
            depth_ratio=result.depth_ratio,
            epoch_offset_durations=result.epoch_offset_durations,
            rationale=rationale.strip(),
        )
        self.dossier.write_envelope(REVIEW, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "verdict": result.verdict,
            "period_ratio": None if result.period_ratio is None else round(result.period_ratio, 6),
            "depth_ratio": None if result.depth_ratio is None else round(result.depth_ratio, 3),
            "epoch_offset_durations": None
            if result.epoch_offset_durations is None
            else round(result.epoch_offset_durations, 3),
            "disagreements": list(result.disagreements),
            "file": REVIEW,
        }
