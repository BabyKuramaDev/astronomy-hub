"""Use case: crossmatch."""

from dataclasses import dataclass
from typing import Any

from contexts.catalog.application.ports import PlanetCatalogs
from contexts.catalog.domain.crossmatch import catalog_status, match_entries, notes
from shared.contracts import CatalogData, CatalogMatch, SignalFile
from shared.mission import CatalogConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.meta import ToolMeta

SIGNAL = "signal.json"
CATALOG = "catalog.json"
CATALOG_NAMES = {
    "pscomppars": "NASA Exoplanet Archive pscomppars",
    "toi": "NASA Exoplanet Archive TOI",
    "ctoi": "ExoFOP CTOI",
}


@dataclass
class Crossmatch:
    catalogs: PlanetCatalogs
    dossier: Dossier
    meta: ToolMeta
    config: CatalogConfig

    def execute(self) -> dict[str, Any]:
        signal_period = None
        if self.dossier.exists(SIGNAL):
            signal = self.dossier.read_envelope(SIGNAL, SignalFile).data
            signal_period = signal.period_days if signal.detected else None
        tic = self.meta.tic_id
        entries = [
            *self.catalogs.confirmed_planets(tic),
            *self.catalogs.tois(tic),
            *self.catalogs.ctois(tic),
        ]
        matched = match_entries(
            entries, signal_period, self.config.period_tolerance, self.config.alias_max_integer
        )
        data = CatalogData(
            status=catalog_status(matched),  # type: ignore[arg-type]
            matches=[
                CatalogMatch(
                    catalog=CATALOG_NAMES.get(m.entry.catalog, m.entry.catalog),
                    id=m.entry.id,
                    period_days=m.entry.period_days,
                    disposition=m.entry.disposition,
                    period_match=m.period_match,
                    url=m.entry.url,  # type: ignore[arg-type]
                )
                for m in matched
            ],
            literature=[],
            notes=notes(matched, signal_period),
        )
        self.dossier.write_envelope(CATALOG, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": tic,
            "status": data.status,
            "signal_period_days": signal_period,
            "matches": [
                {
                    "id": m.entry.id,
                    "catalog": m.entry.catalog,
                    "period_days": m.entry.period_days,
                    "disposition": m.entry.disposition,
                    "period_match": m.period_match,
                    "ratio": m.ratio,
                }
                for m in matched
            ],
            "notes": data.notes,
            "sources": self.catalogs.describe(),
            "file": CATALOG,
        }
