"""Use case: render-report. Reads the dossier through the contracts; writes report.md."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from contexts.reporting.domain.view import VERDICT_TEXT
from shared.contracts import CONTRACTS, DecisionFile
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

REPORT = "report.md"
DECISION = "decision.json"
SIGNAL = "signal.json"
SECTIONS = {
    "signal": "signal.json",
    "search": "search.json",
    "model": "model.json",
    "vetting": "vetting.json",
    "reproduction": "review/reproduction.json",
    "review": "review.json",
    "catalog": "catalog.json",
    "ephemeris": "ephemeris.json",
}

Renderer = Callable[[dict[str, Any]], str]


@dataclass
class RenderReport:
    dossier: Dossier
    meta: ToolMeta
    render: Renderer

    def execute(self, summary: str | None) -> dict[str, Any]:
        if not self.dossier.exists(DECISION):
            raise InvalidInputError("decision.json is missing: run decide before render-report")
        decision = self.dossier.read_envelope(DECISION, DecisionFile)
        envelopes = {DECISION: decision}
        context: dict[str, Any] = {}
        stale = []
        for name, rel in SECTIONS.items():
            context[name] = None
            if not self.dossier.exists(rel):
                continue
            env = self.dossier.read_envelope(rel, CONTRACTS[rel])
            # A file computed on another signal.json belongs to another run: left out.
            if SIGNAL in env.inputs and self.dossier.stale_inputs(env, (SIGNAL,)):
                stale.append(rel)
                continue
            envelopes[rel] = env
            context[name] = env.data
        provenance = [
            {
                "file": rel,
                "context": env.produced_by.context,
                "tool": env.produced_by.tool,
                "version": env.produced_by.version,
                "created": env.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for rel, env in sorted(envelopes.items())
        ]
        text = self.render(
            {
                **context,
                "tic_id": self.meta.tic_id,
                "decision": decision.data,
                "verdict_text": VERDICT_TEXT[decision.data.final],
                "summary": (summary or "").strip(),
                "provenance": provenance,
                "stale": stale,
            }
        )
        self.dossier.write_bytes(REPORT, text.encode("utf-8"))
        return {
            "tic_id": self.meta.tic_id,
            "final": decision.data.final,
            "sections_missing": [
                rel for name, rel in SECTIONS.items() if context[name] is None and rel not in stale
            ],
            "sections_stale": stale,
            "lines": text.count("\n"),
            "file": REPORT,
        }
