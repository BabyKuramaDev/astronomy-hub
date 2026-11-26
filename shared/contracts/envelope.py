"""Common envelope of every JSON file in the dossier."""

import hashlib
import json
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any

from pydantic import AwareDatetime, BaseModel, field_validator

from shared.contracts._base import ContractModel, NonEmptyStr, SemVer, Sha256Digest, Slug, TicId
from shared.kernel.contexts import Context


class ProducedBy(ContractModel):
    context: Context
    tool: Slug
    version: NonEmptyStr


class Envelope[DataT: BaseModel](ContractModel):
    schema_version: SemVer
    tic_id: TicId
    mission: Slug
    produced_by: ProducedBy
    created_at: AwareDatetime
    inputs: dict[str, Sha256Digest]
    data: DataT

    @field_validator("created_at")
    @classmethod
    def _created_at_is_utc(cls, value: AwareDatetime) -> AwareDatetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("created_at must be in UTC")
        return value

    @field_validator("inputs")
    @classmethod
    def _inputs_are_relative_paths(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            path = PurePosixPath(key)
            if not key or "\\" in key or path.is_absolute() or ".." in path.parts:
                raise ValueError(f"input path must be relative to the dossier: {key!r}")
        return value


def canonical_json(model: BaseModel) -> bytes:
    """Serialize a model as canonical JSON: sorted keys, no whitespace, UTF-8."""
    payload = model.model_dump(mode="json")
    text = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def data_sha256(envelope: Envelope[Any]) -> str:
    """Output hash for log.jsonl: computed over `data` only, never over the envelope.

    Two identical runs give the same hash even though `created_at` differs.
    """
    return "sha256:" + hashlib.sha256(canonical_json(envelope.data)).hexdigest()
