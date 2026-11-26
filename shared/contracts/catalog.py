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
    # Catalog value: tfopwg_disp of the TOI list (APC, CP, FA, FP, KP, PC), the TFOPWG
    # disposition of a CTOI, or CONFIRMED for pscomppars.
    disposition: str | None
    # The match's period agrees with signal.json (1% or an integer ratio); null without
    # a detected signal or without a catalog period.
    period_match: bool | None
    url: HttpUrl


class LiteratureRef(ContractModel):
    title: NonEmptyStr
    url: HttpUrl
    note: str


class CatalogData(ContractModel):
    status: CatalogStatus
    matches: list[CatalogMatch]
    literature: list[LiteratureRef]
    notes: list[NonEmptyStr]
