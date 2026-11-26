from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from contexts.vetting.tests.synthetic import make_inputs
from shared.contracts import (
    LightcurveSetData,
    PeriodSearchData,
    SearchPeak,
    SectorLightcurve,
    SignalData,
    StarData,
)
from shared.kernel.contexts import Context
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta

TIC = 4242


def meta(context: Context, tool: str) -> ToolMeta:
    return ToolMeta(context, tool, TIC, "exoplanets", "0.1.0", lambda: datetime.now(UTC))


def write_vetting_dossier(root: Path, **kwargs: object) -> Dossier:
    """A dossier with every file the gates read, from the synthetic control."""
    inputs = make_inputs(**kwargs)  # type: ignore[arg-type]
    dossier = Dossier(root)
    entries = []
    for sector in inputs.raw:
        rel = f"lightcurve/s{sector.sector:04d}.parquet"
        dossier.write_table(
            rel,
            {
                "time_btjd": sector.time,
                "flux": sector.flux * 5e4,
                "flux_err": np.full(sector.time.size, 10.0),
                "centroid_col": sector.centroid_col,
                "centroid_row": sector.centroid_row,
            },
        )
        entries.append(
            SectorLightcurve(
                sector=sector.sector,
                fits_file=f"lightcurve/s{sector.sector:04d}.fits",
                table_file=rel,
                n_cadences=sector.time.size,
                n_valid=sector.time.size,
                t_start_btjd=float(sector.time[0]),
                t_end_btjd=float(sector.time[-1]),
            )
        )
    sectors = [s.sector for s in inputs.raw]
    acq = meta(Context.ACQUISITION, "fetch-lightcurves")
    dossier.write_envelope(
        "lightcurve/manifest.json",
        acq.envelope(
            LightcurveSetData(
                author="SPOC",
                exptime_s=120.0,
                flux_column="PDCSAP_FLUX",
                available_sectors=sectors,
                selection_rule="longest_consecutive_run",
                max_sectors=4,
                sectors=entries,
            ),
            {},
        ),
    )
    dossier.write_table(
        "lightcurve_clean.parquet",
        {
            "time_btjd": inputs.time,
            "flux": inputs.flux,
            "flux_err": inputs.flux_err,
            "sector": inputs.sector.astype(np.int16),
        },
    )
    peak = SearchPeak(
        id="p1",
        period_days=inputs.period_days,
        epoch_btjd=inputs.epoch_btjd,
        duration_hours=inputs.duration_hours,
        depth_ppm=inputs.depth_ppm,
        snr=inputs.snr,
        sde=15.0,
        n_transits=20,
        power=100.0,
    )
    det = meta(Context.DETECTION, "search-period")
    dossier.write_envelope(
        "search.json",
        det.envelope(
            PeriodSearchData(
                method="bls",
                sectors=sectors,
                period_min_days=0.5,
                period_max_days=15.0,
                durations_hours=[2.0],
                bin_minutes=10.0,
                n_periods=100,
                inverted_snr_max=inputs.inverted_snr_max,
                peaks=[peak],
                discarded=[],
            ),
            {},
        ),
    )
    signal = SignalData(
        detected=True,
        period_days=inputs.period_days,
        epoch_btjd=inputs.epoch_btjd,
        duration_hours=inputs.duration_hours,
        depth_ppm=inputs.depth_ppm,
        snr=inputs.snr,
        n_transits=20,
        sectors=sectors,
        method="bls",
        other_peaks=[],
    )
    dossier.write_envelope("signal.json", det.envelope(signal, {}))
    star = StarData(
        ra_deg=10.0,
        dec_deg=-10.0,
        tmag=9.7,
        teff_k=None,
        logg=None,
        radius_rsun=inputs.stellar_radius,
        mass_msun=inputs.stellar_mass,
        contamination_ratio=None,
        source="synthetic",
        neighbor_radius_arcsec=63.0,
        neighbors=[],
    )
    dossier.write_envelope("star.json", acq.envelope(star, {}))
    return dossier
