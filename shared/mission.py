"""Schema and loader of missions/<mission>/mission.yaml.

Every threshold or parameter a tool consumes lives in mission.yaml and is
validated here; nothing mission-specific is hardcoded in a context.
"""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import (
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    ValidationError,
    model_validator,
)

from shared.contracts._base import ContractModel, NonEmptyStr, Slug

MISSIONS_DIR = Path(__file__).resolve().parent.parent / "missions"


class RetryConfig(ContractModel):
    """Transient errors of a remote service are retried with exponential backoff."""

    attempts: PositiveInt
    backoff_s: NonNegativeFloat


class SectorSelection(ContractModel):
    rule: Literal["longest_consecutive_run"]
    max_sectors: PositiveInt


class AcquisitionConfig(ContractModel):
    author: NonEmptyStr
    exptime_s: PositiveFloat
    flux_column: Literal["PDCSAP_FLUX"]
    sector_selection: SectorSelection
    neighbor_radius_arcsec: PositiveFloat
    retry: RetryConfig


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


class QuickFitConfig(ContractModel):
    samples: PositiveInt  # draws from the covariance for the errors of derived quantities


class McmcConfig(ContractModel):
    walkers: PositiveInt
    steps: PositiveInt
    burn: NonNegativeInt
    autocorr_factor: PositiveFloat

    @model_validator(mode="after")
    def _burn_below_steps(self) -> Self:
        if self.burn >= self.steps:
            raise ValueError("burn must be below steps")
        return self


class ModelingConfig(ContractModel):
    seed: NonNegativeInt
    window_durations: PositiveFloat
    jitter_ppm_range: tuple[PositiveFloat, PositiveFloat]
    quick: QuickFitConfig
    mcmc: McmcConfig

    @model_validator(mode="after")
    def _jitter_range(self) -> Self:
        if self.jitter_ppm_range[0] >= self.jitter_ppm_range[1]:
            raise ValueError("jitter_ppm_range must be increasing")
        return self


class CatalogConfig(ContractModel):
    period_tolerance: PositiveFloat  # relative tolerance of a period match
    alias_max_integer: PositiveInt  # integer multiples and submultiples up to this count
    retry: RetryConfig


GateSeverityName = Literal["hard", "soft", "info"]


class MeasurementRange(ContractModel):
    """A measurement parameter of the gates: its default and the range run-gate accepts."""

    default: PositiveFloat
    min: PositiveFloat
    max: PositiveFloat

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.min <= self.default <= self.max:
            raise ValueError("need min <= default <= max")
        return self


class VettingMeasurement(ContractModel):
    duration_scale: MeasurementRange  # multiplies the transit duration of signal.json
    window_durations: MeasurementRange  # outer edge of the local baseline, in durations
    baseline_inner_durations: PositiveFloat  # inner edge of the local baseline (fixed)


class GateBase(ContractModel):
    severity: GateSeverityName


class CoverageGate(GateBase):
    min_sectors: PositiveInt
    min_transits: PositiveInt


class HoldoutGate(GateBase):
    min_z: PositiveFloat
    min_mean_z: PositiveFloat
    period_window: PositiveFloat  # relative half-width of the period grid around P
    n_periods: PositiveInt


class OddEvenGate(GateBase):
    max_sigma: PositiveFloat


class SecondaryGate(GateBase):
    min_sigma: PositiveFloat  # significance of the secondary eclipse
    max_depth_ratio: PositiveFloat  # deeper than this fraction of the primary: not a planet


class PlausibilityGate(GateBase):
    planet_radius_min_rearth: PositiveFloat
    planet_radius_max_rjup: PositiveFloat
    duration_ratio: tuple[PositiveFloat, PositiveFloat]  # T14 / T14 circular with b = 0


class CentroidGate(GateBase):
    max_sigma: PositiveFloat
    max_shift_arcsec: PositiveFloat
    pixel_scale_arcsec: PositiveFloat


class CoherenceGate(GateBase):
    min_positive_fraction: Annotated[float, Field(gt=0, le=1)]
    min_jackknife_snr: PositiveFloat
    min_median_fraction: PositiveFloat


class RotationGate(GateBase):
    max_clean_ratio: PositiveFloat  # sinusoid amplitude / depth, detrended flux
    max_raw_ratio: PositiveFloat  # sinusoid amplitude / depth, raw PDCSAP flux
    oot_durations: PositiveFloat  # out of transit: farther than this many durations


class VettingGates(ContractModel):
    catalog: GateBase
    coverage: CoverageGate
    snr: GateBase
    holdout: HoldoutGate
    odd_even: OddEvenGate = Field(alias="odd-even")
    secondary: SecondaryGate
    plausibility: PlausibilityGate
    centroid: CentroidGate
    coherence: CoherenceGate
    rotation: RotationGate


class VettingConfig(ContractModel):
    measurement: VettingMeasurement
    gates: VettingGates


class MissionConfig(ContractModel):
    name: Slug
    description: NonEmptyStr
    acquisition: AcquisitionConfig
    preparation: PreparationConfig
    detection: DetectionConfig
    modeling: ModelingConfig
    catalog: CatalogConfig
    vetting: VettingConfig


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
