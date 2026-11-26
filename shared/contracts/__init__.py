"""Pydantic models of every JSON file in the dossier.

Tools validate when writing and evals validate when reading.
"""

from shared.contracts._base import SCHEMA_VERSION, ContractModel
from shared.contracts.catalog import CatalogData, CatalogMatch, CatalogStatus, LiteratureRef
from shared.contracts.decision import DecisionData, FinalDecision
from shared.contracts.envelope import Envelope, ProducedBy, canonical_json, data_sha256
from shared.contracts.model import Measurement, ModelData
from shared.contracts.review import ReviewData, ReviewVerdict
from shared.contracts.signal import Peak, SignalData
from shared.contracts.vetting import Gate, GateSeverity, GateStatus, VettingData, VettingVerdict

SignalFile = Envelope[SignalData]
ModelFile = Envelope[ModelData]
CatalogFile = Envelope[CatalogData]
VettingFile = Envelope[VettingData]
ReviewFile = Envelope[ReviewData]
DecisionFile = Envelope[DecisionData]

# Dossier file name -> contract that validates it.
CONTRACTS: dict[str, type[Envelope]] = {
    "signal.json": SignalFile,
    "model.json": ModelFile,
    "catalog.json": CatalogFile,
    "vetting.json": VettingFile,
    "review.json": ReviewFile,
    "decision.json": DecisionFile,
}

__all__ = [
    "CONTRACTS",
    "SCHEMA_VERSION",
    "CatalogData",
    "CatalogFile",
    "CatalogMatch",
    "CatalogStatus",
    "ContractModel",
    "DecisionData",
    "DecisionFile",
    "Envelope",
    "FinalDecision",
    "Gate",
    "GateSeverity",
    "GateStatus",
    "LiteratureRef",
    "Measurement",
    "ModelData",
    "ModelFile",
    "Peak",
    "ProducedBy",
    "ReviewData",
    "ReviewFile",
    "ReviewVerdict",
    "SignalData",
    "SignalFile",
    "VettingData",
    "VettingFile",
    "VettingVerdict",
    "canonical_json",
    "data_sha256",
]
