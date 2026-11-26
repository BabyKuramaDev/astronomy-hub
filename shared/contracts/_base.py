"""Base model and field types shared by every contract."""

from datetime import timedelta
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

SCHEMA_VERSION = "0.1.0"


class ContractModel(BaseModel):
    """Immutable, closed model: unknown fields, NaN and infinities are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _check_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must be relative to the dossier: {value!r}")
    return value


def _check_utc(value: AwareDatetime) -> AwareDatetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("datetime must be in UTC")
    return value


NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")]
SemVer = Annotated[str, StringConstraints(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
TicId = Annotated[int, Field(gt=0)]
RelPath = Annotated[str, AfterValidator(_check_relative_path)]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_check_utc)]
PeakId = Annotated[str, StringConstraints(pattern=r"^p[1-9][0-9]*$")]
