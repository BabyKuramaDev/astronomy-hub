"""Builds the envelope of a tool's output."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from shared.contracts import SCHEMA_VERSION, Envelope, ProducedBy
from shared.kernel.contexts import Context


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ToolMeta:
    context: Context
    tool: str
    tic_id: int
    mission: str
    version: str
    clock: Callable[[], datetime] = utc_now

    def envelope[D: BaseModel](self, data: D, inputs: Mapping[str, str]) -> Envelope[Any]:
        return Envelope[type(data)](  # type: ignore[misc]
            schema_version=SCHEMA_VERSION,
            tic_id=self.tic_id,
            mission=self.mission,
            produced_by=ProducedBy(context=self.context, tool=self.tool, version=self.version),
            created_at=self.clock(),
            inputs=dict(sorted(inputs.items())),
            data=data,
        )
