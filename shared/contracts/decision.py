"""decision.json, written by `direction`."""

from typing import Literal

from pydantic import Field

from shared.contracts._base import ContractModel, NonEmptyStr

FinalDecision = Literal["no_signal", "known", "false_positive", "candidate", "inconclusive"]
# explore: Catalog may stop the case early; eval: blind, Catalog runs last and never decides.
RunMode = Literal["explore", "eval"]


class DecisionData(ContractModel):
    mode: RunMode
    final: FinalDecision
    reason: NonEmptyStr
    next_step: NonEmptyStr
    # M5 phase A: a candidate's tier (A passes every gate, B carries caveats) and the
    # caveats: gates that could not be evaluated, soft gates marginal, transit count.
    tier: Literal["A", "B"] | None = None
    caveats: list[NonEmptyStr] = Field(default_factory=list)
    n_transits: int | None = None
