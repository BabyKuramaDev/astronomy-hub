"""Use case: decide. The final verdict comes from the rule; the agent gives the reason."""

from dataclasses import dataclass
from typing import Any

from contexts.direction.domain.decision import DecisionError, Evidence, decide
from shared.contracts import CatalogFile, DecisionData, ReviewFile, SignalFile, VettingFile
from shared.mission import DirectionConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

SIGNAL = "signal.json"
CATALOG = "catalog.json"
VETTING = "vetting.json"
REVIEW = "review.json"
DECISION = "decision.json"


@dataclass
class Decide:
    dossier: Dossier
    meta: ToolMeta
    config: DirectionConfig

    def _read(self, rel: str, model: type) -> Any:
        """A file of the current signal, or None if it does not exist."""
        if not self.dossier.exists(rel):
            return None
        env = self.dossier.read_envelope(rel, model)
        if self.dossier.stale_inputs(env, (SIGNAL,)):
            raise InvalidInputError(f"{rel} was computed on another signal.json: rerun it")
        return env.data

    def execute(self, mode: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise InvalidInputError("--reason must not be empty")
        signal = self.dossier.read_envelope(SIGNAL, SignalFile).data
        catalog = vetting = review = None
        if signal.detected:
            # Eval mode is blind: catalog.json is never read, even if it exists.
            catalog = self._read(CATALOG, CatalogFile) if mode == "explore" else None
            vetting = self._read(VETTING, VettingFile)
            review = self._read(REVIEW, ReviewFile)
        evidence = Evidence(
            mode=mode,
            detected=signal.detected,
            catalog_status=catalog.status if catalog else None,
            vetting_verdict=vetting.verdict if vetting else None,
            review_verdict=review.verdict if review else None,
        )
        try:
            final, basis = decide(evidence)
        except DecisionError as exc:
            raise InvalidInputError(str(exc)) from exc
        next_step = getattr(self.config.next_steps, final)
        data = DecisionData(mode=mode, final=final, reason=reason.strip(), next_step=next_step)  # type: ignore[arg-type]
        self.dossier.write_envelope(DECISION, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "mode": mode,
            "final": final,
            "basis": basis,
            "next_step": next_step,
            "file": DECISION,
        }
