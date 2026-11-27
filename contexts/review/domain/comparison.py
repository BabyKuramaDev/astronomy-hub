"""review conclude: compare the independent analysis with signal.json by a fixed rule."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tolerances:
    period: float  # relative
    depth: float  # relative
    alias_max_integer: int
    epoch_durations: float = 0.5  # transit times may differ by this fraction of the duration


@dataclass(frozen=True)
class Comparison:
    verdict: str  # reproduced | partial | not_reproduced
    period_ratio: float | None
    depth_ratio: float | None
    disagreements: tuple[str, ...]
    epoch_offset_durations: float | None = None


def alias(ratio: float, tol: float, max_integer: int) -> str | None:
    """ "k/1" or "1/k" when ratio is an integer multiple or submultiple (k >= 2)."""
    for k in range(2, max_integer + 1):
        if abs(ratio / k - 1.0) <= tol:
            return f"{k}/1"
        if abs(ratio * k - 1.0) <= tol:
            return f"1/{k}"
    return None


def epoch_offset(
    epoch: float, period: float, signal_epoch: float, signal_duration_days: float
) -> float:
    """Time from signal.json's epoch to the nearest independent transit, in signal durations."""
    n = round((signal_epoch - epoch) / period)
    return (epoch + n * period - signal_epoch) / signal_duration_days


def compare(
    detected: bool,
    period: float | None,
    depth: float | None,
    sde: float | None,
    sde_min: float,
    signal_period: float,
    signal_depth: float,
    tol: Tolerances,
    epoch: float | None = None,
    signal_epoch: float | None = None,
    signal_duration_hours: float | None = None,
) -> Comparison:
    """Same period, same transit times and same box depth: reproduced. Same period at other
    times or with another depth, or an integer alias of the period: partial. Anything else,
    or no detection: not_reproduced. Depths are box depths, each on its own curve."""
    if not detected or period is None:
        best = "none" if sde is None else f"{sde:.1f}"
        return Comparison(
            "not_reproduced",
            None,
            None,
            (f"the independent search found no peak with SDE >= {sde_min:g} (best {best})",),
        )
    p_ratio = period / signal_period
    d_ratio = depth / signal_depth if depth is not None and depth > 0 else None
    if abs(p_ratio - 1.0) <= tol.period:
        offset = None
        if epoch is not None and signal_epoch is not None and signal_duration_hours:
            offset = epoch_offset(epoch, period, signal_epoch, signal_duration_hours / 24.0)
        if offset is None or abs(offset) > tol.epoch_durations:
            seen = "not measured" if offset is None else f"{offset:+.2f} durations"
            return Comparison(
                "partial",
                p_ratio,
                d_ratio,
                (
                    f"same period but the transits fall at other times: offset {seen} "
                    f"(tolerance {tol.epoch_durations:g})",
                ),
                offset,
            )
        if d_ratio is not None and abs(d_ratio - 1.0) <= tol.depth:
            return Comparison("reproduced", p_ratio, d_ratio, (), offset)
        detail = "not measured" if d_ratio is None else f"{d_ratio:.2f} times"
        return Comparison(
            "partial",
            p_ratio,
            d_ratio,
            (
                f"box depth is {detail} the signal's (tolerance {tol.depth:.0%}): "
                f"{depth:.0f} ppm vs {signal_depth:.0f} ppm"
                if depth is not None
                else f"box depth not measured (tolerance {tol.depth:.0%})",
            ),
            offset,
        )
    found = alias(p_ratio, tol.period, tol.alias_max_integer)
    if found is not None:
        return Comparison(
            "partial",
            p_ratio,
            d_ratio,
            (f"independent period {period:.6f} d is the {found} alias of {signal_period:.6f} d",),
        )
    return Comparison(
        "not_reproduced",
        p_ratio,
        d_ratio,
        (
            f"independent period {period:.6f} d differs from {signal_period:.6f} d "
            f"by {abs(p_ratio - 1):.2%} (tolerance {tol.period:.2%})",
        ),
    )
