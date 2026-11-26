"""Use case: fetch-star."""

from dataclasses import dataclass
from typing import Any

from contexts.acquisition.application.ports import TicCatalog
from contexts.acquisition.domain.star import build_star
from shared.mission import AcquisitionConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import DataNotAvailableError
from shared.toolkit.meta import ToolMeta

STAR = "star.json"


@dataclass
class FetchStar:
    catalog: TicCatalog
    dossier: Dossier
    meta: ToolMeta
    config: AcquisitionConfig

    def execute(self) -> dict[str, Any]:
        radius = self.config.neighbor_radius_arcsec
        target = self.catalog.target(self.meta.tic_id)
        try:
            ra, dec = float(target["ra"]), float(target["dec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DataNotAvailableError(f"TIC {self.meta.tic_id} has no coordinates") from exc
        rows = self.catalog.neighbors(ra, dec, radius)
        star = build_star(target, rows, radius, self.catalog.source(target))
        self.dossier.write_envelope(STAR, self.meta.envelope(star, self.dossier.reads))
        brightest = min(
            (n for n in star.neighbors if n.tmag is not None),
            key=lambda n: n.tmag,  # type: ignore[arg-type, return-value]
            default=None,
        )
        return {
            "tic_id": self.meta.tic_id,
            "tmag": star.tmag,
            "radius_rsun": star.radius_rsun.value if star.radius_rsun else None,
            "teff_k": star.teff_k.value if star.teff_k else None,
            "n_neighbors": len(star.neighbors),
            "brightest_neighbor_tmag": brightest.tmag if brightest else None,
            "file": STAR,
        }
