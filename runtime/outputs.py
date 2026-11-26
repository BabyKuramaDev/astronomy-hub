"""Unpack the dossier tarball a session wrote and validate it against the contracts."""

import io
import tarfile
from pathlib import Path

from pydantic import ValidationError

from shared.contracts import CONTRACTS, FoldFile


def contract_for(rel: str) -> type | None:
    if rel in CONTRACTS:
        return CONTRACTS[rel]
    if rel.startswith("folds/") and rel.endswith(".json"):
        return FoldFile
    return None


def extract(archive: bytes, dest: Path) -> Path:
    """Extract into dest; returns the dossier directory (the archive's single top folder)."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        tops = {Path(m.name).parts[0] for m in tar.getmembers()}
        if len(tops) != 1:
            raise ValueError(f"expected one top-level folder, got {sorted(tops)}")
        tar.extractall(dest, filter="data")
    return dest / tops.pop()


def validate(dossier: Path) -> tuple[list[str], dict[str, str]]:
    """(validated files, {file: error}) for every JSON with a contract."""
    ok, errors = [], {}
    for path in sorted(dossier.rglob("*.json")):
        rel = path.relative_to(dossier).as_posix()
        model = contract_for(rel)
        if model is None:
            continue
        try:
            model.model_validate_json(path.read_bytes())
            ok.append(rel)
        except ValidationError as exc:
            errors[rel] = str(exc).splitlines()[0]
    return ok, errors
