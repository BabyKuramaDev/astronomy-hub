"""Ports of the acquisition context."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from contexts.acquisition.domain.lightcurve import SectorLightcurveRaw


class LightcurveArchive(Protocol):
    def available_sectors(self, tic_id: int, author: str, exptime_s: float) -> list[int]: ...

    def download(
        self, tic_id: int, sectors: Sequence[int], author: str, exptime_s: float, dest: Path
    ) -> dict[int, Path]:
        """Download one light curve file per sector into dest; skip files already there."""
        ...


class LightcurveReader(Protocol):
    def read(self, path: Path, flux_column: str) -> SectorLightcurveRaw: ...


class TicCatalog(Protocol):
    def target(self, tic_id: int) -> Mapping[str, Any]: ...

    def neighbors(
        self, ra_deg: float, dec_deg: float, radius_arcsec: float
    ) -> list[Mapping[str, Any]]: ...

    def source(self, target: Mapping[str, Any]) -> str: ...
