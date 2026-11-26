"""Schema and loader of missions/<mission>/mission.yaml.

Every threshold or parameter a tool consumes lives in mission.yaml and is
validated here; nothing mission-specific is hardcoded in a context.
"""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import (
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    ValidationError,
    model_validator,
)

from shared.contracts._base import ContractModel, NonEmptyStr, Slug

MISSIONS_DIR = Path(__file__).resolve().parent.parent / "missions"


class SectorSelection(ContractModel):
    rule: Literal["longest_consecutive_run"]
    max_sectors: PositiveInt


class AcquisitionConfig(ContractModel):
    author: NonEmptyStr
    exptime_s: PositiveFloat
    flux_column: Literal["PDCSAP_FLUX"]
    sector_selection: SectorSelection
    neighbor_radius_arcsec: PositiveFloat


class PreparationConfig(ContractModel):
    detrend_method: Literal["biweight"]
    window_days: PositiveFloat
    break_tolerance_days: PositiveFloat
    sigma_upper: PositiveFloat


class FoldConfig(ContractModel):
    window_durations: PositiveFloat
    n_bins: Annotated[int, Field(ge=3)]


class DurationLimit(ContractModel):
    """Envelope for the longest possible transit at each period (Kepler's third law)."""

    stellar_density_min_solar: PositiveFloat
    rp_rs_max: Annotated[float, Field(gt=0, lt=1)]


class DetectionConfig(ContractModel):
    period_min_days: PositiveFloat
    period_max_days: PositiveFloat
    durations_hours: Annotated[list[PositiveFloat], Field(min_length=1)]
    duration_limit: DurationLimit
    bin_minutes: PositiveFloat
    frequency_factor: PositiveFloat
    n_peaks: PositiveInt
    examine_factor: PositiveInt
    peak_separation: PositiveFloat
    harmonic_max_integer: Annotated[int, Field(ge=2)]
    harmonic_tolerance: PositiveFloat
    snr_min: PositiveFloat
    floor_mask_durations: PositiveFloat
    min_transits: PositiveInt
    fold: FoldConfig

    @model_validator(mode="after")
    def _period_range(self) -> Self:
        if self.period_min_days >= self.period_max_days:
            raise ValueError("period_min_days must be below period_max_days")
        return self


class ModelingConfig(ContractModel):
    walkers: PositiveInt
    steps: PositiveInt
    burn: NonNegativeInt
    seed: NonNegativeInt
    window_durations: PositiveFloat
    autocorr_factor: PositiveFloat

    @model_validator(mode="after")
    def _burn_below_steps(self) -> Self:
        if self.burn >= self.steps:
            raise ValueError("burn must be below steps")
        return self


class MissionConfig(ContractModel):
    name: Slug
    description: NonEmptyStr
    acquisition: AcquisitionConfig
    preparation: PreparationConfig
    detection: DetectionConfig
    modeling: ModelingConfig


class MissionError(ValueError):
    """mission.yaml is missing or does not match the schema."""


def load_mission(name: str, missions_dir: Path = MISSIONS_DIR) -> MissionConfig:
    path = missions_dir / name / "mission.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MissionError(f"unknown mission {name!r}: {path} not found") from exc
    try:
        config = MissionConfig.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise MissionError(f"invalid {path.name}: {where}: {first['msg']}") from exc
    if config.name != name:
        raise MissionError(f"{path} declares name {config.name!r}, expected {name!r}")
    return config
