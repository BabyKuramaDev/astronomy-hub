"""What the gates read, already loaded from the dossier, and what they return."""

from dataclasses import dataclass, field

import numpy as np

from shared.contracts import Measurement


@dataclass(frozen=True)
class RawSector:
    """One sector before detrending: PDCSAP flux over its median, and the centroid."""

    sector: int
    time: np.ndarray
    flux: np.ndarray
    centroid_col: np.ndarray
    centroid_row: np.ndarray


@dataclass(frozen=True)
class ModelInfo:
    rp_rs: Measurement | None
    planet_radius_rearth: Measurement | None
    duration_hours: Measurement | None
    method: str
    failure: str | None = None  # model.json is a failed fit: no measurement to use


@dataclass(frozen=True)
class CatalogInfo:
    status: str
    known_matches: tuple[str, ...]  # ids of entries that match the signal's period


@dataclass(frozen=True)
class GateInputs:
    period_days: float
    epoch_btjd: float
    duration_hours: float
    depth_ppm: float
    snr: float
    snr_min: float
    inverted_snr_max: float
    time: np.ndarray  # lightcurve_clean.parquet
    flux: np.ndarray
    flux_err: np.ndarray
    sector: np.ndarray
    raw: tuple[RawSector, ...]
    stellar_radius: Measurement | None
    stellar_mass: Measurement | None
    model: ModelInfo | None
    catalog: CatalogInfo | None
    target_tmag: float | None = None
    # TIC neighbors from star.json: (separation in arcsec, Tmag)
    neighbors: tuple[tuple[float, float | None], ...] = ()


@dataclass(frozen=True)
class MeasureParams:
    duration_scale: float
    window_durations: float
    baseline_inner_durations: float


@dataclass(frozen=True)
class GateOutcome:
    status: str  # "pass" | "fail" | "marginal"
    value: float | None
    threshold: float | None
    note: str
    metrics: dict[str, float | None] = field(default_factory=dict)
