"""Use case: decide. The final verdict comes from the rule; the agent gives the reason."""

from dataclasses import dataclass
from typing import Any

from contexts.direction.domain.decision import KNOWN, KNOWN_FALSE, DecisionError, Evidence, decide
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
        # Read only what the rule needs, in its order, so files left over from another
        # run are never consulted. Eval mode is blind: catalog.json is never read.
        catalog = vetting = review = None
        if signal.detected:
            catalog = self._read(CATALOG, CatalogFile) if mode == "explore" else None
            if catalog is None or catalog.status not in KNOWN | KNOWN_FALSE:
                vetting = self._read(VETTING, VettingFile)
                if vetting is not None and vetting.verdict != "false_positive":
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
        # A vetting.json from before tiers says candidate only when every gate passed: A.
        level = (vetting.tier or "A") if final == "candidate" and vetting is not None else None
        caveats = []
        if vetting is not None:  # what could not be checked, and soft doubts
            for g in vetting.gates:
                if g.severity == "info":
                    continue
                if g.status == "not_evaluable":
                    caveats.append(f"{g.id} not evaluable: {g.note}")
                elif g.status == "marginal" and g.severity == "soft":
                    caveats.append(f"{g.id} marginal: {g.note}")
        data = DecisionData(
            mode=mode,  # type: ignore[arg-type]
            final=final,  # type: ignore[arg-type]
            reason=reason.strip(),
            next_step=next_step,
            tier=level,
            caveats=caveats,
            n_transits=signal.n_transits if signal.detected else None,
        )
        self.dossier.write_envelope(DECISION, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "mode": mode,
            "final": final,
            "tier": level,
            "caveats": caveats,
            "basis": basis,
            "next_step": next_step,
            "file": DECISION,
        }
