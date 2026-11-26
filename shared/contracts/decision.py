"""decision.json, written by `direction`."""

from typing import Literal

from shared.contracts._base import ContractModel, NonEmptyStr

FinalDecision = Literal["no_signal", "known", "false_positive", "candidate", "inconclusive"]
# explore: Catalog may stop the case early; eval: blind, Catalog runs last and never decides.
RunMode = Literal["explore", "eval"]


class DecisionData(ContractModel):
    mode: RunMode
    final: FinalDecision
    reason: NonEmptyStr
    next_step: NonEmptyStr
