"""Load the gate inputs from the dossier, recording every file read."""

import numpy as np

from contexts.vetting.domain.inputs import CatalogInfo, GateInputs, ModelInfo, RawSector
from shared.contracts import (
    CatalogFile,
    LightcurveSetFile,
    ModelFile,
    SearchFile,
    SignalFile,
    StarFile,
)
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError

SIGNAL = "signal.json"
SEARCH = "search.json"
CLEAN = "lightcurve_clean.parquet"
MANIFEST = "lightcurve/manifest.json"
STAR = "star.json"
MODEL = "model.json"
CATALOG = "catalog.json"


def _column(table: dict[str, np.ndarray], name: str, size: int) -> np.ndarray:
    """Centroid columns are missing from tables written before M2: NaN then."""
    return np.asarray(table[name], dtype=float) if name in table else np.full(size, np.nan)


def load_inputs(dossier: Dossier, snr_min: float) -> GateInputs:
    signal_env = dossier.read_envelope(SIGNAL, SignalFile)
    signal = signal_env.data
    if not signal.detected:
        raise InvalidInputError("signal.json has detected=false: there is nothing to vet")
    search = dossier.read_envelope(SEARCH, SearchFile).data
    clean = dossier.read_table(CLEAN)
    manifest = dossier.read_envelope(MANIFEST, LightcurveSetFile).data
    raw = []
    for entry in manifest.sectors:
        if entry.n_valid == 0:
            continue
        table = dossier.read_table(entry.table_file)
        flux = np.asarray(table["flux"], dtype=float)
        raw.append(
            RawSector(
                sector=entry.sector,
                time=np.asarray(table["time_btjd"], dtype=float),
                flux=flux / np.median(flux),
                centroid_col=_column(table, "centroid_col", flux.size),
                centroid_row=_column(table, "centroid_row", flux.size),
            )
        )

    star = dossier.read_envelope(STAR, StarFile).data if dossier.exists(STAR) else None
    model = None
    if dossier.exists(MODEL):
        model_env = dossier.read_envelope(MODEL, ModelFile)
        if not dossier.stale_inputs(model_env, (SIGNAL,)):  # a model of another signal is ignored
            m = model_env.data
            model = ModelInfo(
                m.rp_rs, m.planet_radius_rearth, m.duration_hours, m.method, m.failure
            )
    catalog = None
    if dossier.exists(CATALOG):
        cat_env = dossier.read_envelope(CATALOG, CatalogFile)
        if not dossier.stale_inputs(cat_env, (SIGNAL,)):
            known = tuple(m.id for m in cat_env.data.matches if m.period_match)
            catalog = CatalogInfo(cat_env.data.status, known)

    return GateInputs(
        period_days=signal.period_days,  # type: ignore[arg-type]
        epoch_btjd=signal.epoch_btjd,  # type: ignore[arg-type]
        duration_hours=signal.duration_hours,  # type: ignore[arg-type]
        depth_ppm=signal.depth_ppm,  # type: ignore[arg-type]
        snr=signal.snr,  # type: ignore[arg-type]
        snr_min=snr_min,
        inverted_snr_max=search.inverted_snr_max,
        time=np.asarray(clean["time_btjd"], dtype=float),
        flux=np.asarray(clean["flux"], dtype=float),
        flux_err=np.asarray(clean["flux_err"], dtype=float),
        sector=np.asarray(clean["sector"], dtype=np.int64),
        raw=tuple(raw),
        stellar_radius=star.radius_rsun if star else None,
        stellar_mass=star.mass_msun if star else None,
        model=model,
        catalog=catalog,
    )
