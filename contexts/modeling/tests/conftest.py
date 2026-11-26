from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from contexts.modeling.domain.transit import limb_darkening
from shared.contracts import Gate, Measurement, SignalData, StarData, VettingData
from shared.kernel.contexts import Context
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta

TIC = 31
TRUE = {"t0": 1001.2, "period": 1.7, "rp": 0.1, "a": 6.0, "b": 0.3, "q1": 0.4, "q2": 0.3}
DURATION_HOURS = 2.4


def batman_lc(seed: int = 3, noise_ppm: float = 400.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import batman

    time = np.arange(1000.0, 1014.0, 2.0 / 1440.0)
    p = batman.TransitParams()
    p.t0, p.per, p.rp, p.a = TRUE["t0"], TRUE["period"], TRUE["rp"], TRUE["a"]
    p.inc = float(np.degrees(np.arccos(TRUE["b"] / TRUE["a"])))
    p.ecc, p.w, p.limb_dark = 0.0, 90.0, "quadratic"
    p.u = list(limb_darkening(TRUE["q1"], TRUE["q2"]))
    flux = batman.TransitModel(p, time).light_curve(p)
    rng = np.random.default_rng(seed)
    flux = flux + rng.normal(0.0, noise_ppm * 1e-6, time.size)
    return time, flux, np.full(time.size, noise_ppm * 1e-6)


def meta(context: Context, tool: str) -> ToolMeta:
    return ToolMeta(
        context, tool, TIC, "exoplanets", "0.1.0", lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )


def write_dossier(root: Path, *, detected: bool = True, star: str = "with_radius") -> Dossier:
    dossier = Dossier(root)
    time, flux, err = batman_lc()
    dossier.write_table(
        "lightcurve_clean.parquet",
        {
            "time_btjd": time,
            "flux": flux,
            "flux_err": err,
            "sector": np.full(time.size, 5, np.int16),
        },
    )
    signal = (
        SignalData(
            detected=True,
            period_days=TRUE["period"] * 1.0001,
            epoch_btjd=TRUE["t0"] + 0.002,
            duration_hours=DURATION_HOURS,
            depth_ppm=11000.0,
            snr=80.0,
            n_transits=8,
            sectors=[5],
            method="bls",
            other_peaks=[],
        )
        if detected
        else SignalData(detected=False, sectors=[5], method="bls", other_peaks=[])
    )
    dossier.write_envelope(
        "signal.json", meta(Context.DETECTION, "select-peak").envelope(signal, {})
    )
    if star != "missing":
        radius = (
            Measurement(value=1.0, err_lower=0.05, err_upper=0.1) if star == "with_radius" else None
        )
        data = StarData(
            ra_deg=10.0,
            dec_deg=-10.0,
            tmag=10.0,
            teff_k=None,
            logg=None,
            radius_rsun=radius,
            mass_msun=None,
            contamination_ratio=None,
            source="test TIC",
            neighbor_radius_arcsec=63.0,
            neighbors=[],
        )
        dossier.write_envelope(
            "star.json", meta(Context.ACQUISITION, "fetch-star").envelope(data, {})
        )
    return dossier


@pytest.fixture
def dossier_root(tmp_path: Path) -> Path:
    write_dossier(tmp_path)
    return tmp_path


def write_vetting(root: Path, verdict: str = "candidate") -> None:
    """vetting.json computed on the current signal.json."""
    dossier = Dossier(root)
    dossier.record_read("signal.json")
    gate = Gate(
        id="odd-even", status="pass", severity="hard", value=0.5, threshold=2.5, note="", n_runs=1
    )
    data = VettingData(gates=[gate], verdict=verdict, rationale="test")  # type: ignore[arg-type]
    dossier.write_envelope(
        "vetting.json", meta(Context.VETTING, "conclude").envelope(data, dossier.reads)
    )
