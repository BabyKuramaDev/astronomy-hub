"""Use cases: run-gates (every gate once) and run-gate (one gate, other parameters)."""

from dataclasses import dataclass
from typing import Any

from contexts.vetting.application.loader import SIGNAL, load_inputs
from contexts.vetting.domain.gates import GATES, GateSpec, gate_spec
from contexts.vetting.domain.inputs import GateInputs, MeasureParams
from contexts.vetting.domain.verdict import GateStatus, combine, verdict
from shared.contracts import GateRun, GateRunsData, GateRunsFile
from shared.mission import MeasurementRange, VettingConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

RUNS = "vetting/runs.json"


def gate_config(config: VettingConfig, gate_id: str) -> Any:
    return getattr(config.gates, gate_id.replace("-", "_"))


def measure_params(
    config: VettingConfig, duration_scale: float | None, window_durations: float | None
) -> MeasureParams:
    m = config.measurement

    def pick(name: str, value: float | None, rng: MeasurementRange) -> float:
        if value is None:
            return rng.default
        if not rng.min <= value <= rng.max:
            raise InvalidInputError(f"--{name} must be within [{rng.min:g}, {rng.max:g}]")
        return value

    return MeasureParams(
        duration_scale=pick("duration-scale", duration_scale, m.duration_scale),
        window_durations=pick("window-durations", window_durations, m.window_durations),
        baseline_inner_durations=m.baseline_inner_durations,
    )


def run_gate(
    spec: GateSpec,
    number: int,
    inputs: GateInputs,
    params: MeasureParams,
    config: VettingConfig,
) -> GateRun:
    cfg = gate_config(config, spec.id)
    outcome = spec.fn(inputs, params, cfg)
    used = (
        {"duration-scale": params.duration_scale, "window-durations": params.window_durations}
        if spec.rerunnable
        else {}
    )
    return GateRun(
        gate=spec.id,
        run=number,
        params=used,
        status=outcome.status,  # type: ignore[arg-type]
        severity=cfg.severity,
        value=outcome.value,
        threshold=outcome.threshold,
        note=outcome.note,
        metrics=outcome.metrics,
    )


def provisional_verdict(runs: GateRunsData) -> str:
    statuses = []
    for spec in GATES:
        mine = runs.of(spec.id)
        if mine:
            statuses.append(
                GateStatus(spec.id, combine([r.status for r in mine]), mine[0].severity)
            )
    return verdict(statuses)


def _row(run: GateRun) -> dict[str, Any]:
    return {
        "gate": run.gate,
        "run": run.run,
        "status": run.status,
        "severity": run.severity,
        "value": run.value,
        "threshold": run.threshold,
        "note": run.note,
    }


@dataclass
class RunGates:
    dossier: Dossier
    meta: ToolMeta
    config: VettingConfig
    sde_min: float

    def execute(self) -> dict[str, Any]:
        inputs = load_inputs(self.dossier, self.sde_min)
        params = measure_params(self.config, None, None)
        runs = GateRunsData(runs=[run_gate(spec, 1, inputs, params, self.config) for spec in GATES])
        self.dossier.write_envelope(RUNS, self.meta.envelope(runs, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "gates": [_row(r) for r in runs.runs],
            "verdict_if_concluded": provisional_verdict(runs),
            "file": RUNS,
        }


@dataclass
class RunGate:
    dossier: Dossier
    meta: ToolMeta
    config: VettingConfig
    sde_min: float

    def execute(
        self, gate_id: str, duration_scale: float | None, window_durations: float | None
    ) -> dict[str, Any]:
        spec = gate_spec(gate_id)
        if spec is None:
            known = ", ".join(g.id for g in GATES)
            raise InvalidInputError(f"unknown gate {gate_id!r} (gates: {known})")
        if not spec.rerunnable:
            raise InvalidInputError(
                f"gate {gate_id} has no measurement parameters: rerunning it changes nothing"
            )
        params = measure_params(self.config, duration_scale, window_durations)
        if not self.dossier.exists(RUNS):
            raise InvalidInputError(f"{RUNS} not found: run run-gates first")
        previous = self.dossier.read_envelope(RUNS, GateRunsFile)
        if self.dossier.stale_inputs(previous, (SIGNAL,)):
            raise InvalidInputError(f"{RUNS} was computed on another signal.json: run run-gates")
        runs = list(previous.data.runs)
        mine = [r for r in runs if r.gate == gate_id]
        wanted = {
            "duration-scale": params.duration_scale,
            "window-durations": params.window_durations,
        }
        same = next((r for r in mine if r.params == wanted), None)
        if same is None:
            inputs = load_inputs(self.dossier, self.sde_min)
            same = run_gate(spec, len(mine) + 1, inputs, params, self.config)
            runs.append(same)
        data = GateRunsData(runs=runs)
        inputs_hashes = {**previous.inputs, **self.dossier.reads}
        self.dossier.write_envelope(RUNS, self.meta.envelope(data, inputs_hashes))
        statuses = [r.status for r in data.of(gate_id)]
        return {
            "tic_id": self.meta.tic_id,
            "run": _row(same),
            "params": same.params,
            "gate_runs": statuses,
            "gate_status_if_concluded": combine(statuses),
            "verdict_if_concluded": provisional_verdict(data),
            "file": RUNS,
        }
