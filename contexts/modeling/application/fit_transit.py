"""Use case: fit-transit."""

from dataclasses import dataclass
from typing import Any

from contexts.modeling.domain.fit import (
    ChainSettings,
    FitError,
    fit_transit,
    planet_radius,
)
from contexts.modeling.domain.transit import Guess
from shared.contracts import Measurement, ModelData, SignalFile, StarFile
from shared.mission import ModelingConfig
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

CLEAN = "lightcurve_clean.parquet"
SIGNAL = "signal.json"
STAR = "star.json"
MODEL = "model.json"


def _compact(m: Measurement, digits: int = 5) -> list[float]:
    return [round(m.value, digits), round(m.err_lower, digits), round(m.err_upper, digits)]


@dataclass(frozen=True)
class FitOverrides:
    walkers: int | None = None
    steps: int | None = None
    burn: int | None = None
    seed: int | None = None


@dataclass
class FitTransit:
    dossier: Dossier
    meta: ToolMeta
    config: ModelingConfig

    def execute(self, overrides: FitOverrides | None = None) -> dict[str, Any]:
        o = overrides or FitOverrides()
        cfg = self.config
        settings = ChainSettings(
            walkers=o.walkers or cfg.walkers,
            steps=o.steps or cfg.steps,
            burn=cfg.burn if o.burn is None else o.burn,
            seed=cfg.seed if o.seed is None else o.seed,
            autocorr_factor=cfg.autocorr_factor,
        )
        signal = self.dossier.read_envelope(SIGNAL, SignalFile).data
        if not signal.detected:
            raise InvalidInputError("signal.json has detected=false: there is no transit to fit")
        table = self.dossier.read_table(CLEAN)
        stellar_radius = None
        if self.dossier.exists(STAR):
            star = self.dossier.read_envelope(STAR, StarFile).data
            stellar_radius = star.radius_rsun
            source = star.source
        guess = Guess(
            t0=signal.epoch_btjd,  # type: ignore[arg-type]
            period=signal.period_days,  # type: ignore[arg-type]
            duration_days=signal.duration_hours / 24.0,  # type: ignore[operator]
            depth=signal.depth_ppm * 1e-6,  # type: ignore[operator]
        )
        try:
            fit = fit_transit(
                table["time_btjd"],
                table["flux"],
                table["flux_err"],
                guess,
                settings,
                cfg.window_durations,
            )
        except FitError as exc:
            raise InvalidInputError(str(exc)) from exc

        warnings = []
        if stellar_radius is not None:
            radius = planet_radius(fit.rp_rs_samples, stellar_radius, settings.seed)
            stellar_source: str | None = source
        else:
            radius, stellar_source = None, None
            warnings.append(
                "star.json has no stellar radius with its error: planet_radius_rearth is null"
                if self.dossier.exists(STAR)
                else "star.json not found: planet_radius_rearth is null"
            )
        conv = fit.convergence
        if not conv.converged:
            warnings.append(
                f"chain not converged: {conv.n_post_burn} post-burn steps, "
                f"need more than {conv.autocorr_factor:g} x tau_max "
                f"({'unknown' if conv.tau_max is None else round(conv.tau_max, 1)})"
            )

        data = ModelData(
            rp_rs=fit.rp_rs,
            planet_radius_rearth=radius,
            impact_parameter=fit.impact_parameter,
            a_rs=fit.a_rs,
            stellar_source=stellar_source,
        )
        self.dossier.write_envelope(MODEL, self.meta.envelope(data, self.dossier.reads))
        return {
            "tic_id": self.meta.tic_id,
            "columns": ["value", "err_lower", "err_upper"],
            "rp_rs": _compact(fit.rp_rs),
            "impact_parameter": _compact(fit.impact_parameter, 3),
            "a_rs": _compact(fit.a_rs, 3),
            "planet_radius_rearth": _compact(radius, 3) if radius else None,
            "t0_btjd": _compact(fit.t0, 6),
            "period_days": _compact(fit.period, 7),
            "n_points": fit.n_points,
            "chain": {
                "walkers": settings.walkers,
                "steps": settings.steps,
                "burn": settings.burn,
                "seed": settings.seed,
            },
            "convergence": {
                "converged": conv.converged,
                "tau_max": None if conv.tau_max is None else round(conv.tau_max, 1),
                "n_post_burn": conv.n_post_burn,
                "autocorr_factor": conv.autocorr_factor,
                "acceptance_mean": round(conv.acceptance_mean, 3),
                "acceptance_min": round(conv.acceptance_min, 3),
            },
            "warnings": warnings,
            "file": MODEL,
        }
