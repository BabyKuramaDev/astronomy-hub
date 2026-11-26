"""Use case: fetch-lightcurves."""

from dataclasses import dataclass
from typing import Any

import numpy as np

from contexts.acquisition.application.ports import LightcurveArchive, LightcurveReader
from contexts.acquisition.domain.lightcurve import valid_mask
from contexts.acquisition.domain.sectors import select_sectors
from shared.contracts import LightcurveSetData, SectorLightcurve
from shared.mission import AcquisitionConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import DataNotAvailableError, InvalidInputError
from shared.toolkit.meta import ToolMeta

LIGHTCURVE_DIR = "lightcurve"
MANIFEST = "lightcurve/manifest.json"


def sector_table(sector: int) -> str:
    return f"{LIGHTCURVE_DIR}/s{sector:04d}.parquet"


@dataclass
class FetchLightcurves:
    archive: LightcurveArchive
    reader: LightcurveReader
    dossier: Dossier
    meta: ToolMeta
    config: AcquisitionConfig

    def execute(self) -> dict[str, Any]:
        cfg = self.config
        tic_id = self.meta.tic_id
        available = sorted(set(self.archive.available_sectors(tic_id, cfg.author, cfg.exptime_s)))
        if not available:
            raise DataNotAvailableError(
                f"no {cfg.author} {cfg.exptime_s:g} s light curves for TIC {tic_id}"
            )
        chosen = select_sectors(available, cfg.sector_selection.max_sectors)
        files = self.archive.download(
            tic_id, chosen, cfg.author, cfg.exptime_s, self.dossier.path(LIGHTCURVE_DIR)
        )
        missing = sorted(set(chosen) - set(files))
        if missing:
            raise DataNotAvailableError(f"download returned no file for sectors {missing}")

        entries = []
        for sector in chosen:
            fits_rel = files[sector].relative_to(self.dossier.root).as_posix()
            self.dossier.record_existing_write(fits_rel)
            raw = self.reader.read(self.dossier.record_read(fits_rel), cfg.flux_column)
            if raw.tic_id != tic_id or raw.sector != sector:
                raise InvalidInputError(
                    f"{fits_rel} is TIC {raw.tic_id} sector {raw.sector}, "
                    f"expected TIC {tic_id} sector {sector}"
                )
            mask = valid_mask(raw)
            time = raw.time_btjd[mask].astype(np.float64)
            self.dossier.write_table(
                sector_table(sector),
                {
                    "time_btjd": time,
                    "flux": raw.flux[mask].astype(np.float64),
                    "flux_err": raw.flux_err[mask].astype(np.float64),
                },
            )
            finite_time = raw.time_btjd[np.isfinite(raw.time_btjd)]
            entries.append(
                SectorLightcurve(
                    sector=sector,
                    fits_file=fits_rel,
                    table_file=sector_table(sector),
                    n_cadences=raw.n_cadences,
                    n_valid=int(mask.sum()),
                    t_start_btjd=float(finite_time.min()),
                    t_end_btjd=float(finite_time.max()),
                )
            )
        if sum(e.n_valid for e in entries) == 0:
            raise DataNotAvailableError(f"no valid cadences in sectors {chosen}")

        data = LightcurveSetData(
            author=cfg.author,
            exptime_s=cfg.exptime_s,
            flux_column=cfg.flux_column,
            available_sectors=available,
            selection_rule=cfg.sector_selection.rule,
            max_sectors=cfg.sector_selection.max_sectors,
            sectors=entries,
        )
        self.dossier.write_envelope(MANIFEST, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": tic_id,
            "available_sectors": available,
            "sectors": chosen,
            "n_valid": {str(e.sector): e.n_valid for e in entries},
            "manifest": MANIFEST,
        }
