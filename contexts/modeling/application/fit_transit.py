"""Use case: fit-transit.

quick (default) runs in seconds; mcmc only runs on a candidate that passed vetting,
that is, when vetting.json says candidate and was computed on the current signal.json.
"""

from dataclasses import dataclass
from typing import Any, Literal

from contexts.modeling.domain.fit import (
    ChainSettings,
    FitError,
    FitResult,
    FitSettings,
    FitSettingsError,
    fit_mcmc,
    fit_quick,
    geometry_problem,
    planet_radius,
)
from contexts.modeling.domain.transit import Guess
from shared.contracts import (
    McmcConvergence,
    Measurement,
    ModelData,
    SignalFile,
    StarFile,
    VettingFile,
)
from shared.mission import ModelingConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

CLEAN = "lightcurve_clean.parquet"
SIGNAL = "signal.json"
STAR = "star.json"
VETTING = "vetting.json"
MODEL = "model.json"


def _compact(m: Measurement | None, digits: int = 5) -> list[float] | None:
    if m is None:
        return None
    return [round(m.value, digits), round(m.err_lower, digits), round(m.err_upper, digits)]


@dataclass(frozen=True)
class FitOverrides:
    walkers: int | None = None
    steps: int | None = None
    burn: int | None = None
    seed: int | None = None

    def chain_given(self) -> bool:
        return any(v is not None for v in (self.walkers, self.steps, self.burn))


@dataclass
class FitTransit:
    dossier: Dossier
    meta: ToolMeta
    config: ModelingConfig

    def _require_candidate(self) -> None:
        if not self.dossier.exists(VETTING):
            raise InvalidInputError("--mode mcmc needs vetting.json: run vetting first")
        vetting = self.dossier.read_envelope(VETTING, VettingFile)
        if vetting.data.verdict != "candidate":
            raise InvalidInputError(
                f"--mode mcmc only runs on candidates; vetting.json says {vetting.data.verdict}"
            )
        if self.dossier.stale_inputs(vetting, (SIGNAL,)):
            raise InvalidInputError("vetting.json was computed on another signal.json")

    def execute(
        self, mode: Literal["quick", "mcmc"] = "quick", overrides: FitOverrides | None = None
    ) -> dict[str, Any]:
        o = overrides or FitOverrides()
        cfg = self.config
        if mode == "quick" and o.chain_given():
            raise InvalidInputError("--walkers, --steps and --burn need --mode mcmc")
        settings = FitSettings(
            seed=cfg.seed if o.seed is None else o.seed,
            window_durations=cfg.window_durations,
            jitter_min=cfg.jitter_ppm_range[0] * 1e-6,
            jitter_max=cfg.jitter_ppm_range[1] * 1e-6,
        )
        chain = ChainSettings(
            walkers=o.walkers or cfg.mcmc.walkers,
            steps=o.steps or cfg.mcmc.steps,
            burn=cfg.mcmc.burn if o.burn is None else o.burn,
            autocorr_factor=cfg.mcmc.autocorr_factor,
        )
        signal = self.dossier.read_envelope(SIGNAL, SignalFile).data
        if not signal.detected:
            raise InvalidInputError("signal.json has detected=false: there is no transit to fit")
        if mode == "mcmc":
            self._require_candidate()
        table = self.dossier.read_table(CLEAN)
        stellar_radius, source = None, None
        if self.dossier.exists(STAR):
            star = self.dossier.read_envelope(STAR, StarFile).data
            stellar_radius, source = star.radius_rsun, star.source
        guess = Guess(
            t0=signal.epoch_btjd,  # type: ignore[arg-type]
            period=signal.period_days,  # type: ignore[arg-type]
            duration_days=signal.duration_hours / 24.0,  # type: ignore[operator]
            depth=signal.depth_ppm * 1e-6,  # type: ignore[operator]
        )
        args = (table["time_btjd"], table["flux"], table["flux_err"], guess, settings)
        try:
            fit = fit_quick(*args, cfg.quick.samples) if mode == "quick" else fit_mcmc(*args, chain)
            failure = geometry_problem(fit)
        except FitSettingsError as exc:
            raise InvalidInputError(str(exc)) from exc
        except FitError as exc:
            failure = str(exc)
        if failure is not None:
            return self._failed(mode, failure)

        warnings = []
        radius = None
        if stellar_radius is not None:
            radius = planet_radius(fit.rp_rs_samples, stellar_radius, settings.seed)
        else:
            source = None
            warnings.append(
                "star.json has no stellar radius with its error: planet_radius_rearth is null"
                if self.dossier.exists(STAR)
                else "star.json not found: planet_radius_rearth is null"
            )
        convergence = self._convergence(fit, chain, settings.seed, warnings)
        data = ModelData(
            method=fit.method,  # type: ignore[arg-type]
            rp_rs=fit.rp_rs,
            planet_radius_rearth=radius,
            impact_parameter=fit.impact_parameter,
            a_rs=fit.a_rs,
            period_days=fit.period,
            epoch_btjd=fit.t0,
            duration_hours=fit.duration_hours,
            jitter_ppm=fit.jitter_ppm,
            stellar_source=source,
            convergence=convergence,
        )
        self.dossier.write_envelope(MODEL, self.meta.envelope(data, self.dossier.reads))
        summary: dict[str, Any] = {
            "tic_id": self.meta.tic_id,
            "method": fit.method,
            "columns": ["value", "err_lower", "err_upper"],
            "rp_rs": _compact(fit.rp_rs),
            "impact_parameter": _compact(fit.impact_parameter, 3),
            "a_rs": _compact(fit.a_rs, 3),
            "planet_radius_rearth": _compact(radius, 3),
            "epoch_btjd": _compact(fit.t0, 6),
            "period_days": _compact(fit.period, 7),
            "duration_hours": _compact(fit.duration_hours, 3),
            "jitter_ppm": _compact(fit.jitter_ppm, 1),
            "n_points": fit.n_points,
        }
        if convergence is not None:
            summary["convergence"] = convergence.model_dump(mode="json")
        summary |= {"warnings": warnings, "file": MODEL}
        return summary

    def _failed(self, mode: str, failure: str) -> dict[str, Any]:
        """A failed fit is a result: model.json with status failed and its reason."""
        data = ModelData(
            method=mode,  # type: ignore[arg-type]
            status="failed",
            failure=failure,
            rp_rs=None,
            planet_radius_rearth=None,
            impact_parameter=None,
            a_rs=None,
            period_days=None,
            epoch_btjd=None,
            duration_hours=None,
            jitter_ppm=None,
            stellar_source=None,
            convergence=None,
        )
        self.dossier.write_envelope(MODEL, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "method": mode,
            "status": "failed",
            "failure": failure,
            "file": MODEL,
        }

    @staticmethod
    def _convergence(
        fit: FitResult, chain: ChainSettings, seed: int, warnings: list[str]
    ) -> McmcConvergence | None:
        conv = fit.convergence
        if conv is None:
            return None
        if not conv.converged:
            warnings.append(
                f"chain not converged: {conv.n_post_burn} post-burn steps, "
                f"need more than {conv.autocorr_factor:g} x tau_max "
                f"({'unknown' if conv.tau_max is None else round(conv.tau_max, 1)})"
            )
        return McmcConvergence(
            walkers=chain.walkers,
            steps=chain.steps,
            burn=chain.burn,
            seed=seed,
            tau_max=None if conv.tau_max is None else round(conv.tau_max, 2),
            n_post_burn=conv.n_post_burn,
            autocorr_factor=conv.autocorr_factor,
            converged=conv.converged,
            acceptance_mean=round(conv.acceptance_mean, 4),
            acceptance_min=round(conv.acceptance_min, 4),
        )
