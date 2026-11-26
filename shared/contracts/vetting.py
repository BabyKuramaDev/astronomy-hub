"""vetting/runs.json and vetting.json, written by `vetting`."""

from typing import Annotated, Literal, Self

from pydantic import Field, PositiveInt, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr, Slug

GateStatus = Literal["pass", "fail", "marginal"]
# hard: a failure means false_positive; soft: a failure means inconclusive;
# info: reported, never part of the verdict.
GateSeverity = Literal["hard", "soft", "info"]
VettingVerdict = Literal["candidate", "false_positive", "inconclusive"]


class GateRun(ContractModel):
    """One run of one gate (run-gates or run-gate), with the parameters it used."""

    gate: Slug
    run: PositiveInt
    params: dict[Slug, float]
    status: GateStatus
    severity: GateSeverity
    value: float | None
    threshold: float | None
    note: str
    metrics: dict[str, float | None]


class GateRunsData(ContractModel):
    runs: Annotated[list[GateRun], Field(min_length=1)]

    @model_validator(mode="after")
    def _runs_are_numbered(self) -> Self:
        seen: dict[str, list[int]] = {}
        for run in self.runs:
            seen.setdefault(run.gate, []).append(run.run)
        for gate, numbers in seen.items():
            if numbers != list(range(1, len(numbers) + 1)):
                raise ValueError(f"runs of gate {gate!r} must be numbered 1, 2, ... in order")
        return self

    def of(self, gate: str) -> list[GateRun]:
        return [r for r in self.runs if r.gate == gate]


class Gate(ContractModel):
    id: Slug
    status: GateStatus
    severity: GateSeverity
    value: float | None
    threshold: float | None
    note: str
    n_runs: PositiveInt  # runs combined: all pass -> pass, all fail -> fail, else marginal


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
