"""One line of log.jsonl, appended by every tool run."""

from pydantic import JsonValue, NonNegativeFloat, NonNegativeInt

from shared.contracts._base import (
    ContractModel,
    NonEmptyStr,
    RelPath,
    Sha256Digest,
    Slug,
    UtcDatetime,
)
from shared.kernel.contexts import Context


class LogEntry(ContractModel):
    ts: UtcDatetime
    context: Context
    tool: Slug
    argv: list[str]
    version: NonEmptyStr
    duration_s: NonNegativeFloat
    exit_code: NonNegativeInt
    # JSON outputs hash their `data`; other files hash their bytes.
    outputs: dict[RelPath, Sha256Digest]
    summary: dict[str, JsonValue] | None
    reason: str | None
    error: str | None
