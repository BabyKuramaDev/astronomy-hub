"""catalog.json, written by `catalog`."""

from typing import Literal

from pydantic import HttpUrl, PositiveFloat

from shared.contracts._base import ContractModel, NonEmptyStr

CatalogStatus = Literal[
    "known_planet",
    "toi",
    "ctoi",
    "known_false_positive",
    "eclipsing_binary",
    "unknown",
]


class CatalogMatch(ContractModel):
    catalog: NonEmptyStr
    id: NonEmptyStr
    period_days: PositiveFloat | None
    # Free string until the ExoFOP disposition values are confirmed.
    disposition: str | None
    url: HttpUrl


class LiteratureRef(ContractModel):
    title: NonEmptyStr
    url: HttpUrl
    note: str


class CatalogData(ContractModel):
    status: CatalogStatus
    matches: list[CatalogMatch]
    literature: list[LiteratureRef]
