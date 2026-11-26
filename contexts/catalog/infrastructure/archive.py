"""Adapters: NASA Exoplanet Archive (TAP: pscomppars, toi) and ExoFOP (CTOI).

Every request is retried on transient errors (shared.toolkit.retry); other
failures become DataNotAvailableError (exit 3).
"""

import json
import math
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from contexts.catalog.domain.crossmatch import CONFIRMED, CatalogEntry
from shared.toolkit.errors import DataNotAvailableError
from shared.toolkit.retry import RetryPolicy

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
OVERVIEW_URL = "https://exoplanetarchive.ipac.caltech.edu/overview/"
EXOFOP_TARGET = "https://exofop.ipac.caltech.edu/tess/target.php"
USER_AGENT = "astronomy-hub/0.1"
TIMEOUT_S = 60

Fetch = Callable[[str], Any]


def pscomppars_query(tic_id: int) -> str:
    return f"select pl_name,pl_orbper from pscomppars where tic_id='TIC {tic_id}'"


def toi_query(tic_id: int) -> str:
    return f"select toi,tfopwg_disp,pl_orbper from toi where tid={tic_id}"


def tap_url(query: str) -> str:
    return TAP_URL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})


def exofop_url(tic_id: int) -> str:
    return f"{EXOFOP_TARGET}?id={tic_id}&json"


def http_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.load(response)


def _period(value: Any) -> float | None:
    try:
        period = float(value)
    except (TypeError, ValueError):
        return None
    return period if math.isfinite(period) and period > 0 else None


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def parse_confirmed(rows: list[dict[str, Any]]) -> list[CatalogEntry]:
    return [
        CatalogEntry(
            catalog="pscomppars",
            id=str(row["pl_name"]),
            period_days=_period(row.get("pl_orbper")),
            disposition=CONFIRMED,
            url=OVERVIEW_URL + urllib.parse.quote(str(row["pl_name"])),
        )
        for row in rows
    ]


def parse_tois(rows: list[dict[str, Any]], tic_id: int) -> list[CatalogEntry]:
    return [
        CatalogEntry(
            catalog="toi",
            id=f"TOI-{row['toi']}",
            period_days=_period(row.get("pl_orbper")),
            disposition=_text(row.get("tfopwg_disp")),
            url=exofop_url(tic_id).removesuffix("&json"),
        )
        for row in rows
    ]


def parse_ctois(target: dict[str, Any], tic_id: int) -> list[CatalogEntry]:
    """CTOIs of an ExoFOP target; the period lives in planet_parameters under the same name."""
    periods = {
        p["name"]: _period(p.get("per"))
        for p in target.get("planet_parameters", [])
        if isinstance(p, dict) and p.get("name")
    }
    entries = []
    for ctoi in target.get("ctois", []):
        name = str(ctoi["ctoi"])
        entries.append(
            CatalogEntry(
                catalog="ctoi",
                id=name,
                period_days=periods.get(name),
                disposition=_text(ctoi.get("tdisp")) or _text(ctoi.get("cdisp")),
                url=exofop_url(tic_id).removesuffix("&json"),
            )
        )
    return entries


class ArchiveCatalogs:
    def __init__(self, retry: RetryPolicy | None = None, fetch: Fetch = http_json) -> None:
        self.retry = retry or RetryPolicy()
        self.fetch = fetch

    def _get(self, what: str, url: str) -> Any:
        try:
            return self.retry.call(lambda: self.fetch(url))
        except Exception as exc:
            raise DataNotAvailableError(f"{what} failed: {type(exc).__name__}: {exc}") from exc

    def confirmed_planets(self, tic_id: int) -> list[CatalogEntry]:
        return parse_confirmed(self._get("pscomppars query", tap_url(pscomppars_query(tic_id))))

    def tois(self, tic_id: int) -> list[CatalogEntry]:
        return parse_tois(self._get("TOI query", tap_url(toi_query(tic_id))), tic_id)

    def ctois(self, tic_id: int) -> list[CatalogEntry]:
        return parse_ctois(self._get("ExoFOP target query", exofop_url(tic_id)), tic_id)

    def describe(self) -> str:
        return "NASA Exoplanet Archive TAP (pscomppars, toi); ExoFOP target JSON (ctois)"
