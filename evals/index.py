"""Resumable record of finished stars: one JSON line per star and version key.

A star already in the index under the same key (set hash, TIC and every version
that can change the result) is not run again.
"""

import hashlib
import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from evals.scoring import Outcome

_LOCK = threading.Lock()


def version_key(**versions: Any) -> str:
    text = json.dumps(versions, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]


class Index:
    def __init__(self, path: Path) -> None:
        self.path = path

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def done(self, key: str, redo_incomplete: bool = False) -> set[int]:
        """Stars finished under this key; with redo_incomplete, a star whose last run
        ended without a decision counts as not done."""
        last = {int(r["tic_id"]): r["outcome"]["status"] for r in self.rows() if r["key"] == key}
        return {t for t, status in last.items() if not (redo_incomplete and status == "incomplete")}

    def outcomes(self, key: str) -> dict[int, Outcome]:
        """The last outcome of each star under this key."""
        return {int(r["tic_id"]): Outcome(**r["outcome"]) for r in self.rows() if r["key"] == key}

    def add(self, key: str, outcome: Outcome, **extra: Any) -> None:
        row = {"key": key, "tic_id": outcome.tic_id, "outcome": asdict(outcome), **extra}
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
