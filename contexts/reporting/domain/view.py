"""Formatting for the report: every number goes out with the file it came from."""

import math

from shared.contracts import Measurement

DASH = "\u2013"  # en dash for a missing value
MINUS = "\u2212"


def num(value: float | None, digits: int = 4) -> str:
    """Significant digits, no exponent for ordinary magnitudes; a dash for missing."""
    if value is None or not math.isfinite(value):
        return DASH
    if value == 0:
        return "0"
    magnitude = math.floor(math.log10(abs(value)))
    decimals = max(0, digits - 1 - magnitude)
    return f"{value:.{decimals}f}"


def measurement(m: Measurement | None, digits: int = 4) -> str:
    """value (-lower/+upper), or value ± err when symmetric to the shown precision."""
    if m is None:
        return DASH
    lower, upper = num(m.err_lower, 2), num(m.err_upper, 2)
    if lower == upper:
        return f"{num(m.value, digits)} ± {lower}"
    return f"{num(m.value, digits)} ({MINUS}{lower} / +{upper})"


def compact(value: float | None, digits: int = 4) -> str:
    """Up to `digits` significant digits without trailing zeros (gate values)."""
    if value is None or not math.isfinite(value):
        return DASH
    return f"{value:.{digits}g}"


VERDICT_TEXT = {
    "candidate": "candidate: the signal survives every vetting gate and an independent "
    "reproduction",
    "false_positive": "false positive",
    "inconclusive": "inconclusive",
    "known": "already catalogued at this period",
    "no_signal": "no signal",
}
