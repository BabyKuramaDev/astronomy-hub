"""review.json, written by `review`."""

from typing import Literal, Self

from pydantic import PositiveFloat, model_validator

from shared.contracts._base import ContractModel, NonEmptyStr

ReviewVerdict = Literal["reproduced", "partial", "not_reproduced"]


class ReviewData(ContractModel):
    period_days_independent: PositiveFloat | None
    depth_ppm_independent: PositiveFloat | None
    disagreements: list[NonEmptyStr]
    verdict: ReviewVerdict

    @model_validator(mode="after")
    def _reproduced_has_independent_values(self) -> Self:
        if self.verdict == "reproduced" and (
            self.period_days_independent is None or self.depth_ppm_independent is None
        ):
            raise ValueError("verdict=reproduced requires independent period and depth")
        return self
