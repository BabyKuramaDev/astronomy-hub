"""Ports of the catalog context."""

from typing import Protocol

from contexts.catalog.domain.crossmatch import CatalogEntry


class PlanetCatalogs(Protocol):
    def confirmed_planets(self, tic_id: int) -> list[CatalogEntry]:
        """Confirmed planets of the star (NASA Exoplanet Archive, pscomppars)."""
        ...

    def tois(self, tic_id: int) -> list[CatalogEntry]:
        """TESS Objects of Interest of the star, with the TFOPWG disposition."""
        ...

    def ctois(self, tic_id: int) -> list[CatalogEntry]:
        """Community TOIs of the star (ExoFOP)."""
        ...

    def describe(self) -> str:
        """Where the entries come from, for the summary."""
        ...
