from typing import Any

import pytest
from pydantic import ValidationError

from shared.contracts import CatalogData


@pytest.fixture
def catalog_data() -> dict[str, Any]:
    return {
        "status": "known_planet",
        "matches": [
            {
                "catalog": "NASA Exoplanet Archive",
                "id": "WASP-18 b",
                "period_days": 0.9414,
                "disposition": "CONFIRMED",
                "url": "https://exoplanetarchive.ipac.caltech.edu/overview/WASP-18b",
            }
        ],
        "literature": [
            {
                "title": "Discovery paper",
                "url": "https://example.org/paper",
                "note": "Period and radius.",
            }
        ],
    }


def test_valid_catalog(catalog_data: dict[str, Any]) -> None:
    assert CatalogData.model_validate(catalog_data).status == "known_planet"


def test_unknown_with_no_matches_is_valid() -> None:
    data = CatalogData.model_validate({"status": "unknown", "matches": [], "literature": []})
    assert data.matches == []


def test_disposition_is_free_text(catalog_data: dict[str, Any]) -> None:
    match = {**catalog_data["matches"][0], "disposition": "PC (planet candidate)"}
    assert CatalogData.model_validate({**catalog_data, "matches": [match]})


def test_match_period_and_disposition_may_be_null(catalog_data: dict[str, Any]) -> None:
    match = {**catalog_data["matches"][0], "period_days": None, "disposition": None}
    assert CatalogData.model_validate({**catalog_data, "matches": [match]})


def test_status_must_be_known_value(catalog_data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CatalogData.model_validate({**catalog_data, "status": "planet"})


@pytest.mark.parametrize("url", ["not a url", "ftp://example.org/x", ""])
def test_urls_must_be_http(catalog_data: dict[str, Any], url: str) -> None:
    ref = {**catalog_data["literature"][0], "url": url}
    with pytest.raises(ValidationError):
        CatalogData.model_validate({**catalog_data, "literature": [ref]})


def test_literature_shape_is_closed(catalog_data: dict[str, Any]) -> None:
    ref = {**catalog_data["literature"][0], "year": 2009}
    with pytest.raises(ValidationError):
        CatalogData.model_validate({**catalog_data, "literature": [ref]})
