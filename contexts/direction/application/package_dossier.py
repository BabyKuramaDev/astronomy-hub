"""Use case: package-dossier. Validates the dossier and packs it for the session outputs.

The only tool that writes outside the dossier: Managed Agents collects the files
written to /mnt/session/outputs/, and one tarball keeps the dossier's layout
(the platform does not say whether it keeps subdirectories).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.contracts import CONTRACTS, FoldFile
from shared.toolkit.dossier import CACHE_DIR, Dossier
from shared.toolkit.errors import DataNotAvailableError, InvalidInputError
from shared.toolkit.meta import ToolMeta

DECISION = "decision.json"

# (dossier root, files relative to it, destination) -> sha256 of the archive
Packer = Callable[[Path, list[str], Path], str]
LOG = "log.jsonl"


def contract_for(rel: str) -> type | None:
    if rel in CONTRACTS:
        return CONTRACTS[rel]
    if rel.startswith("folds/") and rel.endswith(".json"):
        return FoldFile
    return None


@dataclass
class PackageDossier:
    dossier: Dossier
    meta: ToolMeta
    pack: Packer
    # Writes this run's log line before packing, so the archive carries it.
    log_now: Callable[[dict[str, Any]], None] | None = None

    def execute(self, dest_dir: Path) -> dict[str, Any]:
        root = self.dossier.root
        if not self.dossier.exists(DECISION):
            raise DataNotAvailableError("decision.json is missing: run decide before packaging")
        files = sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).parts[0] != CACHE_DIR
        )
        validated = []
        for rel in files:
            model = contract_for(rel)
            if model is not None:
                self.dossier.read_envelope(rel, model)  # raises InvalidInputError
                validated.append(rel)
        if not dest_dir.is_absolute():
            raise InvalidInputError("--dest must be an absolute path")
        dest = dest_dir / f"dossier-{self.meta.tic_id}.tar.gz"
        summary: dict[str, Any] = {
            "tic_id": self.meta.tic_id,
            "archive": str(dest),
            "n_files": len(files) + (LOG not in files),
            "validated": validated,
        }
        if self.log_now is not None:
            self.log_now(summary)  # the archive's own hash cannot be in a file inside it
            if LOG not in files:
                files = sorted([*files, LOG])
        summary["sha256"] = self.pack(root, files, dest)
        return summary
