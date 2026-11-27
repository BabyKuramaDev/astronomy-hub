"""Score dossiers against the labels: pure functions over plain records.

A star's record says what the tools wrote (from signal.json, vetting.json,
review.json and decision.json) and how the run went; the label says its group and
catalog period. Contaminated runs (audit flags) and stars without data are reported
apart, never as failures; a run that ended without a decision is a failure.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

PERIOD_TOLERANCE = 0.01  # spec: within 1 percent of the catalog
ALIAS_MAX = 10
GROUPS = ("planet_deep", "planet_small", "false_positive", "no_signal")
PLANETS = ("planet_deep", "planet_small")


@dataclass(frozen=True)
class Outcome:
    tic_id: int
    status: str  # ok | no_data | contaminated | incomplete
    detected: bool | None = None
    period_days: float | None = None
    final: str | None = None
    vetting: str | None = None
    review: str | None = None
    cost_cents: int = 0
    active_seconds: float = 0.0
    flags: int = 0
    run: str | None = None
    fit: str | None = None  # fitted | failed | crashed (fit-transit raised)


def period_match(found: float | None, catalog: float | None) -> bool:
    if found is None or catalog is None:
        return False
    return abs(found / catalog - 1.0) <= PERIOD_TOLERANCE


def alias(found: float | None, catalog: float | None) -> str | None:
    if found is None or catalog is None:
        return None
    ratio = found / catalog
    for k in range(2, ALIAS_MAX + 1):
        if abs(ratio / k - 1.0) <= PERIOD_TOLERANCE:
            return f"{k}/1"
        if abs(ratio * k - 1.0) <= PERIOD_TOLERANCE:
            return f"1/{k}"
    return None


def grade(label: dict[str, Any], out: Outcome) -> int:
    """0 wrong, 1 partly right, 2 right: used to compare two runs of one star."""
    group, final = label["group"], out.final
    if group in PLANETS:
        if final == "candidate" and period_match(out.period_days, label["period_days"]):
            return 2
        return 1 if period_match(out.period_days, label["period_days"]) else 0
    if group == "false_positive":
        return {"false_positive": 2, "candidate": 0}.get(final or "", 1)
    return {"no_signal": 2, "candidate": 0}.get(final or "", 1)


@dataclass
class GroupStats:
    n: int = 0
    detected: int = 0
    final_ok: int = 0
    candidate_wrong_period: int = 0
    accepted_false_positive: int = 0
    rejected_false_positive: int = 0
    false_alarm: int = 0
    detections_to_review: list[int] = field(default_factory=list)
    inconclusive: int = 0
    reproduced: int = 0
    incomplete: int = 0
    no_signal_correct: int = 0
    fit_failed: int = 0
    fp_rejected_catalog_period: int = 0
    fp_rejected_other_period: int = 0
    fp_not_detected: int = 0

    def rates(self, group: str) -> dict[str, float | None]:
        """Only the metrics that mean something for the group; the rest stay None."""

        def rate(k: int) -> float | None:
            return round(k / self.n, 3) if self.n else None

        out: dict[str, float | None] = dict.fromkeys(
            (
                "detection_recall",
                "final_recall",
                "false_positive_rejected",
                "false_positive_accepted",
                "no_signal_correct",
                "false_alarm",
            )
        )
        if group in PLANETS:
            out["detection_recall"] = rate(self.detected)
            out["final_recall"] = rate(self.final_ok)
        elif group == "false_positive":
            out["false_positive_rejected"] = rate(self.rejected_false_positive)
            out["false_positive_accepted"] = rate(self.accepted_false_positive)
        else:
            out["no_signal_correct"] = rate(self.no_signal_correct)
            out["false_alarm"] = rate(self.false_alarm)
        out["inconclusive"] = rate(self.inconclusive)
        out["reproduced"] = rate(self.reproduced)
        return out


def score(labels: Sequence[dict[str, Any]], outcomes: dict[int, Outcome]) -> dict[str, Any]:
    order = {"calib": 0, "dev": 1, "holdout": 2}
    stats: dict[tuple[str, str], GroupStats] = {}
    grave, aliases, apart, rows = [], [], [], []
    for label in labels:
        tic = int(label["tic_id"])
        out = outcomes.get(tic)
        if out is None:
            continue
        group, catalog = label["group"], label.get("period_days")
        rows.append(
            {
                "tic_id": tic,
                "group": group,
                "split": label["split"],
                "status": out.status,
                "final": out.final,
                "period_days": out.period_days,
                "catalog_period": catalog,
                "grade": grade(label, out),
                "cost_cents": out.cost_cents,
                "active_seconds": out.active_seconds,
                "flags": out.flags,
                "run": out.run,
            }
        )
        if out.status in ("no_data", "contaminated"):
            apart.append({"tic_id": tic, "group": group, "status": out.status, "flags": out.flags})
            continue
        st = stats.setdefault((label["split"], group), GroupStats())
        st.n += 1
        st.fit_failed += out.fit in ("failed", "crashed")
        if out.status == "incomplete":
            st.incomplete += 1
            continue
        matched = period_match(out.period_days, catalog)
        if group in PLANETS:
            st.detected += matched
            st.final_ok += out.final == "candidate" and matched
            st.candidate_wrong_period += out.final == "candidate" and not matched
            if out.final == "false_positive":
                grave.append({"tic_id": tic, "group": group, "period_days": out.period_days})
            if (found := alias(out.period_days, catalog)) is not None:
                aliases.append({"tic_id": tic, "group": group, "ratio": found})
        elif group == "false_positive":
            st.accepted_false_positive += out.final == "candidate"
            st.rejected_false_positive += out.final == "false_positive"
            st.fp_rejected_catalog_period += out.final == "false_positive" and matched
            st.fp_rejected_other_period += out.final == "false_positive" and not matched
            st.fp_not_detected += out.final == "no_signal"
        else:
            st.false_alarm += out.final == "candidate"
            st.no_signal_correct += out.final == "no_signal"
            if out.detected:
                st.detections_to_review.append(tic)
        st.inconclusive += out.final == "inconclusive"
        st.reproduced += out.review == "reproduced"
    table = []
    for split_name, group in sorted(stats, key=lambda k: (order.get(k[0], 9), GROUPS.index(k[1]))):
        st = stats[(split_name, group)]
        if st.n:
            table.append(
                {
                    "split": split_name,
                    "group": group,
                    "n": st.n,
                    **st.rates(group),
                    "candidate_wrong_period": st.candidate_wrong_period
                    if group in PLANETS
                    else None,
                    "incomplete": st.incomplete,
                    "fit_failed": st.fit_failed,
                    "fp_breakdown": {
                        "rejected_catalog_period": st.fp_rejected_catalog_period,
                        "rejected_other_period": st.fp_rejected_other_period,
                        "not_detected": st.fp_not_detected,
                        "inconclusive": st.inconclusive,
                        "accepted": st.accepted_false_positive,
                    }
                    if group == "false_positive"
                    else None,
                    "detections_to_review": sorted(st.detections_to_review),
                }
            )
    scored = [r for r in rows if r["status"] not in ("no_data",)]
    return {
        "table": table,
        "grave_errors": grave,
        "aliases": aliases,
        "apart": apart,
        "rows": rows,
        "cost": {
            "total_cents": sum(r["cost_cents"] for r in rows),
            "per_star_cents": round(sum(r["cost_cents"] for r in scored) / len(scored), 1)
            if scored
            else None,
            "active_seconds_per_star": round(
                sum(r["active_seconds"] for r in scored) / len(scored), 1
            )
            if scored
            else None,
        },
    }


def compare(
    labels: Sequence[dict[str, Any]], agent: dict[int, Outcome], baseline: dict[int, Outcome]
) -> list[dict[str, Any]]:
    """Stars where the agents chose differently from the script, and whether that helped."""
    out = []
    for label in labels:
        tic = int(label["tic_id"])
        a, b = agent.get(tic), baseline.get(tic)
        if a is None or b is None or "no_data" in (a.status, b.status):
            continue
        same_period = (a.period_days is None and b.period_days is None) or (
            a.period_days is not None
            and b.period_days is not None
            and abs(a.period_days / b.period_days - 1) <= PERIOD_TOLERANCE
        )
        if same_period and a.final == b.final and a.detected == b.detected:
            continue
        ga, gb = grade(label, a), grade(label, b)
        out.append(
            {
                "tic_id": tic,
                "group": label["group"],
                "agent": {"final": a.final, "period_days": a.period_days, "grade": ga},
                "baseline": {"final": b.final, "period_days": b.period_days, "grade": gb},
                "effect": "better" if ga > gb else "worse" if ga < gb else "same",
            }
        )
    return out
