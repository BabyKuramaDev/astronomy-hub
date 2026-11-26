"""Common envelope of every JSON file in the dossier."""

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from shared.contracts._base import (
    ContractModel,
    NonEmptyStr,
    RelPath,
    SemVer,
    Sha256Digest,
    Slug,
    TicId,
    UtcDatetime,
)
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
    created_at: UtcDatetime
    inputs: dict[RelPath, Sha256Digest]
    data: DataT


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
