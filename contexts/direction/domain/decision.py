"""The Director's rule for decision.json: a fixed rule, never an average of opinions."""

from dataclasses import dataclass

KNOWN = frozenset({"known_planet", "toi", "ctoi"})
KNOWN_FALSE = frozenset({"known_false_positive", "eclipsing_binary"})


class DecisionError(ValueError):
    """A file the rule needs is missing."""


@dataclass(frozen=True)
class Evidence:
    mode: str  # "explore" | "eval"
    detected: bool
    catalog_status: str | None  # only read in explore mode
    vetting_verdict: str | None
    review_verdict: str | None


def decide(ev: Evidence) -> tuple[str, str]:
    """(final, which evidence decided it).

    no_signal without detection. In explore mode, Catalog cuts first: a match at the
    signal's period (aliases included) is known, or false_positive when the match is a
    known false positive. Then: vetting false_positive is false_positive; candidate only
    with vetting candidate and review reproduced; anything else is inconclusive.
    """
    if not ev.detected:
        return "no_signal", "signal.json: detected=false"
    if ev.mode == "explore":
        if ev.catalog_status is None:
            raise DecisionError("explore mode needs catalog.json: run crossmatch first")
        if ev.catalog_status in KNOWN:
            return "known", f"catalog.json: {ev.catalog_status} at the signal's period"
        if ev.catalog_status in KNOWN_FALSE:
            return "false_positive", f"catalog.json: {ev.catalog_status} at the signal's period"
    if ev.vetting_verdict is None:
        raise DecisionError("vetting.json is missing: run vetting first")
    if ev.vetting_verdict == "false_positive":
        return "false_positive", "vetting.json: false_positive"
    if ev.review_verdict is None:
        raise DecisionError("review.json is missing: run review first")
    if ev.vetting_verdict == "candidate" and ev.review_verdict == "reproduced":
        return "candidate", "vetting.json: candidate; review.json: reproduced"
    return (
        "inconclusive",
        f"vetting.json: {ev.vetting_verdict}; review.json: {ev.review_verdict}",
    )
