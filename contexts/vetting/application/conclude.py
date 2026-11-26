"""Use case: conclude. The verdict comes from the rule; the agent only gives the rationale."""

from dataclasses import dataclass
from typing import Any

from contexts.vetting.application.run_gates import RUNS
from contexts.vetting.domain.gates import GATE_IDS
from contexts.vetting.domain.verdict import GateStatus, combine, verdict
from shared.contracts import Gate, GateRunsFile, SignalFile, VettingData
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

SIGNAL = "signal.json"
VETTING = "vetting.json"


@dataclass
class Conclude:
    dossier: Dossier
    meta: ToolMeta

    def execute(self, rationale: str) -> dict[str, Any]:
        if not rationale.strip():
            raise InvalidInputError("--rationale must not be empty")
        if not self.dossier.exists(RUNS):
            raise InvalidInputError(f"{RUNS} not found: run run-gates first")
        runs_env = self.dossier.read_envelope(RUNS, GateRunsFile)
        if self.dossier.stale_inputs(runs_env, (SIGNAL,)):
            raise InvalidInputError(f"{RUNS} was computed on another signal.json: run run-gates")
        self.dossier.read_envelope(SIGNAL, SignalFile)  # records its hash in inputs
        runs = runs_env.data
        missing = [g for g in GATE_IDS if not runs.of(g)]
        if missing:
            raise InvalidInputError(f"no runs for gates {missing}: run run-gates")

        gates = []
        for gate_id in GATE_IDS:
            mine = runs.of(gate_id)
            first = mine[0]
            status = combine([r.status for r in mine])
            note = first.note
            if len(mine) > 1:
                note += f" | {len(mine)} runs: " + ", ".join(
                    f"{r.status} ({', '.join(f'{k}={v:g}' for k, v in r.params.items())})"
                    for r in mine
                )
            gates.append(
                Gate(
                    id=gate_id,
                    status=status,  # type: ignore[arg-type]
                    severity=first.severity,
                    value=first.value,
                    threshold=first.threshold,
                    note=note,
                    n_runs=len(mine),
                )
            )
        result = verdict([GateStatus(g.id, g.status, g.severity) for g in gates])
        data = VettingData(gates=gates, verdict=result, rationale=rationale.strip())  # type: ignore[arg-type]
        self.dossier.write_envelope(VETTING, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "verdict": result,
            "gates": {
                g.id: f"{g.status} ({g.severity}, {g.n_runs} run{'s' * (g.n_runs > 1)})"
                for g in gates
            },
            "file": VETTING,
        }
