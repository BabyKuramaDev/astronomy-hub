"""signal.json, written by `detection`."""

from typing import Annotated, Self

from pydantic import Field, NonNegativeFloat, PositiveFloat, PositiveInt, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr

# Required when detected=true, must be null when detected=false.
DETECTION_FIELDS = (
    "period_days",
    "epoch_btjd",
    "duration_hours",
    "depth_ppm",
    "snr",
    "n_transits",
)


class Peak(ContractModel):
    period_days: PositiveFloat
    snr: NonNegativeFloat
    depth_ppm: PositiveFloat


class SignalData(ContractModel):
    detected: bool
    period_days: PositiveFloat | None = None
    epoch_btjd: float | None = None
    duration_hours: PositiveFloat | None = None
    depth_ppm: PositiveFloat | None = None
    snr: NonNegativeFloat | None = None
    n_transits: PositiveInt | None = None
    sectors: Annotated[list[PositiveInt], Field(min_length=1)]
    method: NonEmptyStr
    other_peaks: list[Peak]

    @model_validator(mode="after")
    def _detection_fields_match_detected(self) -> Self:
        if self.detected:
            missing = [name for name in DETECTION_FIELDS if getattr(self, name) is None]
            if missing:
                raise ValueError(f"detected=true requires {', '.join(missing)}")
        else:
            present = [name for name in DETECTION_FIELDS if getattr(self, name) is not None]
            if present:
                raise ValueError(f"detected=false requires null {', '.join(present)}")
        if len(set(self.sectors)) != len(self.sectors):
            raise ValueError("sectors must not repeat")
        return self
