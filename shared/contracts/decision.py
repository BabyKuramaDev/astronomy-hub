"""decision.json, written by `direction`."""

from typing import Literal

from shared.contracts._base import ContractModel, NonEmptyStr

FinalDecision = Literal["no_signal", "known", "false_positive", "candidate", "inconclusive"]


class DecisionData(ContractModel):
    final: FinalDecision
    reason: NonEmptyStr
    next_step: NonEmptyStr
