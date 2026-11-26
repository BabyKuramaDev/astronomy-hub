"""Pydantic models of every JSON file in the dossier.

Tools validate when writing and evals validate when reading.
"""

from shared.contracts._base import SCHEMA_VERSION, ContractModel
from shared.contracts.catalog import CatalogData, CatalogMatch, CatalogStatus, LiteratureRef
from shared.contracts.decision import DecisionData, FinalDecision
from shared.contracts.envelope import Envelope, ProducedBy, canonical_json, data_sha256
from shared.contracts.fold import FoldBin, FoldData, OddEven
from shared.contracts.lightcurve import (
    CLEAN_TABLE_COLUMNS,
    SECTOR_TABLE_COLUMNS,
    LightcurveSetData,
    SectorLightcurve,
)
from shared.contracts.log import LogEntry
from shared.contracts.model import Measurement, ModelData
from shared.contracts.review import ReviewData, ReviewVerdict
from shared.contracts.search import DiscardedPeak, PeriodSearchData, SearchPeak
from shared.contracts.signal import Peak, SignalData
from shared.contracts.star import Neighbor, StarData
from shared.contracts.vetting import Gate, GateSeverity, GateStatus, VettingData, VettingVerdict

SignalFile = Envelope[SignalData]
ModelFile = Envelope[ModelData]
CatalogFile = Envelope[CatalogData]
VettingFile = Envelope[VettingData]
ReviewFile = Envelope[ReviewData]
DecisionFile = Envelope[DecisionData]
StarFile = Envelope[StarData]
LightcurveSetFile = Envelope[LightcurveSetData]
SearchFile = Envelope[PeriodSearchData]
FoldFile = Envelope[FoldData]  # folds/<tag>.json

# Dossier file name -> contract that validates it.
CONTRACTS: dict[str, type[Envelope]] = {
    "lightcurve/manifest.json": LightcurveSetFile,
    "star.json": StarFile,
    "search.json": SearchFile,
    "signal.json": SignalFile,
    "model.json": ModelFile,
    "catalog.json": CatalogFile,
    "vetting.json": VettingFile,
    "review.json": ReviewFile,
    "decision.json": DecisionFile,
}

__all__ = [
    "CLEAN_TABLE_COLUMNS",
    "CONTRACTS",
    "SCHEMA_VERSION",
    "SECTOR_TABLE_COLUMNS",
    "CatalogData",
    "CatalogFile",
    "CatalogMatch",
    "CatalogStatus",
    "ContractModel",
    "DecisionData",
    "DecisionFile",
    "DiscardedPeak",
    "Envelope",
    "FinalDecision",
    "FoldBin",
    "FoldData",
    "FoldFile",
    "Gate",
    "GateSeverity",
    "GateStatus",
    "LightcurveSetData",
    "LightcurveSetFile",
    "LiteratureRef",
    "LogEntry",
    "Measurement",
    "ModelData",
    "ModelFile",
    "Neighbor",
    "OddEven",
    "Peak",
    "PeriodSearchData",
    "ProducedBy",
    "ReviewData",
    "ReviewFile",
    "ReviewVerdict",
    "SearchFile",
    "SearchPeak",
    "SectorLightcurve",
    "SignalData",
    "SignalFile",
    "StarData",
    "StarFile",
    "VettingData",
    "VettingFile",
    "VettingVerdict",
    "canonical_json",
    "data_sha256",
]
