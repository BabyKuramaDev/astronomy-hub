"""Base model and field types shared by every contract."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SCHEMA_VERSION = "0.1.0"


class ContractModel(BaseModel):
    """Immutable, closed model: unknown fields, NaN and infinities are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")]
SemVer = Annotated[str, StringConstraints(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
TicId = Annotated[int, Field(gt=0)]
