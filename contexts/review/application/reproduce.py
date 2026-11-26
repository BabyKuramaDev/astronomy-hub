"""Use case: reproduce. Never reads signal.json, model.json or vetting.json."""

import os
from dataclasses import dataclass
from typing import Any

import numpy as np

from contexts.review.domain.reproduction import (
    RawSector,
    ReproductionError,
    ReproductionParams,
    reproduce,
)
from shared.contracts import LightcurveSetFile, ReproductionData
from shared.mission import ReviewConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import DataNotAvailableError
from shared.toolkit.meta import ToolMeta

MANIFEST = "lightcurve/manifest.json"
REPRODUCTION = "review/reproduction.json"
FORBIDDEN = ("signal.json", "model.json", "vetting.json", "search.json")


def params_from(cfg: ReviewConfig) -> ReproductionParams:
    return ReproductionParams(
        detrend_method=cfg.detrend_method,
        detrend_window_days=cfg.detrend_window_days,
        break_tolerance_days=cfg.break_tolerance_days,
        sigma_upper=cfg.sigma_upper,
        bin_minutes=cfg.bin_minutes,
        period_min_days=cfg.period_min_days,
        period_max_days=cfg.period_max_days,
        min_transits=cfg.min_transits,
        sde_min=cfg.sde_min,
        oversampling_factor=cfg.oversampling_factor,
        duration_grid_step=cfg.duration_grid_step,
        threads=os.cpu_count() or 1,
    )


@dataclass
class Reproduce:
    dossier: Dossier
    meta: ToolMeta
    config: ReviewConfig

    def execute(self) -> dict[str, Any]:
        manifest = self.dossier.read_envelope(MANIFEST, LightcurveSetFile).data
        sectors = []
        for entry in manifest.sectors:
            if entry.n_valid == 0:
                continue
            table = self.dossier.read_table(entry.table_file)
            sectors.append(
                RawSector(
                    entry.sector,
                    np.asarray(table["time_btjd"], dtype=float),
                    np.asarray(table["flux"], dtype=float),
                    np.asarray(table["flux_err"], dtype=float),
                )
            )
        try:
            result = reproduce(sectors, params_from(self.config))
        except ReproductionError as exc:
            raise DataNotAvailableError(str(exc)) from exc
        assert not set(self.dossier.reads) & set(FORBIDDEN), "reproduce read another analysis"
        cfg = self.config
        data = ReproductionData(
            detrend_method=cfg.detrend_method,
            detrend_window_days=cfg.detrend_window_days,
            search_method="tls",
            sectors=[s.sector for s in sectors],
            period_min_days=cfg.period_min_days,
            period_max_days=result.period_max_days,
            detected=result.detected,
            sde_min=cfg.sde_min,
            period_days=result.period_days,
            epoch_btjd=result.epoch_btjd,
            duration_hours=result.duration_hours,
            depth_ppm=result.depth_ppm,
            sde=result.sde,
            snr=result.snr,
            n_transits=result.n_transits,
        )
        self.dossier.write_envelope(REPRODUCTION, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "method": f"{cfg.detrend_method} detrending + tls",
            "detected": result.detected,
            "period_days": None if result.period_days is None else round(result.period_days, 6),
            "duration_hours": None
            if result.duration_hours is None
            else round(result.duration_hours, 3),
            "depth_ppm": None if result.depth_ppm is None else round(result.depth_ppm, 1),
            "sde": None if result.sde is None else round(result.sde, 2),
            "sde_min": cfg.sde_min,
            "n_transits": result.n_transits,
            "warnings": list(result.warnings),
            "file": REPRODUCTION,
        }
