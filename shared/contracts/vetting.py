"""vetting.json, written by `vetting`."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr, Slug

GateStatus = Literal["pass", "fail", "marginal"]
# Which gates are hard is decided in M2.
GateSeverity = Literal["hard", "soft"]
VettingVerdict = Literal["candidate", "false_positive", "inconclusive"]


class Gate(ContractModel):
    id: Slug
    status: GateStatus
    severity: GateSeverity
    value: float | None
    threshold: float | None
    note: str


class VettingData(ContractModel):
    gates: Annotated[list[Gate], Field(min_length=1)]
    verdict: VettingVerdict
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def _gate_ids_are_unique(self) -> Self:
        ids = [gate.id for gate in self.gates]
        if len(set(ids)) != len(ids):
            raise ValueError("gate ids must be unique")
        return self
