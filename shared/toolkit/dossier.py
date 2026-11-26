"""The dossier of one star: workspace/<mission>/<tic_id>/.

Every read is recorded with its file hash (the envelope `inputs`), and every
write with its output hash (for log.jsonl).
"""

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel

from shared.contracts import Envelope, LogEntry, data_sha256
from shared.contracts._base import _check_relative_path
from shared.toolkit.errors import DataNotAvailableError, InvalidInputError

LOG_FILE = "log.jsonl"
CACHE_DIR = ".cache"


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class Dossier:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.reads: dict[str, str] = {}
        self.writes: dict[str, str] = {}

    @classmethod
    def for_target(cls, workspace: Path, mission: str, tic_id: int) -> "Dossier":
        return cls(workspace / mission / str(tic_id))

    @property
    def cache_dir(self) -> Path:
        return self.root / CACHE_DIR

    def path(self, rel: str) -> Path:
        _check_relative_path(rel)
        return self.root / rel

    def exists(self, rel: str) -> bool:
        return self.path(rel).exists()

    def _require(self, rel: str) -> Path:
        path = self.path(rel)
        if not path.is_file():
            raise DataNotAvailableError(f"{rel} not found in dossier {self.root}")
        return path

    def _atomic_write(self, rel: str, payload: bytes) -> Path:
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path

    # JSON envelopes -------------------------------------------------------------------

    def read_envelope[M: BaseModel](self, rel: str, model: type[M]) -> M:
        path = self._require(rel)
        payload = path.read_bytes()
        try:
            envelope = model.model_validate_json(payload)
        except ValueError as exc:
            raise InvalidInputError(f"{rel} does not match its contract: {exc}") from exc
        self.reads[rel] = sha256_bytes(payload)
        return envelope

    def write_envelope(self, rel: str, envelope: Envelope[Any]) -> str:
        payload = (envelope.model_dump_json(indent=2) + "\n").encode("utf-8")
        self._atomic_write(rel, payload)
        digest = data_sha256(envelope)
        self.writes[rel] = digest
        return digest

    # Tables ---------------------------------------------------------------------------

    def read_table(self, rel: str) -> dict[str, np.ndarray]:
        path = self._require(rel)
        table = pq.read_table(path)
        self.reads[rel] = sha256_file(path)
        return {name: table.column(name).to_numpy() for name in table.column_names}

    def write_table(self, rel: str, columns: dict[str, np.ndarray]) -> str:
        table = pa.table({name: pa.array(values) for name, values in columns.items()})
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd")
        return self.write_bytes(rel, sink.getvalue().to_pybytes())

    # Raw files ------------------------------------------------------------------------

    def record_read(self, rel: str) -> Path:
        path = self._require(rel)
        self.reads[rel] = sha256_file(path)
        return path

    def record_existing_write(self, rel: str) -> str:
        """Register a file that an adapter wrote directly (for example a download)."""
        digest = sha256_file(self._require(rel))
        self.writes[rel] = digest
        return digest

    def write_bytes(self, rel: str, payload: bytes) -> str:
        self._atomic_write(rel, payload)
        digest = sha256_bytes(payload)
        self.writes[rel] = digest
        return digest

    # log.jsonl ------------------------------------------------------------------------

    def append_log(self, entry: LogEntry) -> None:
        path = self.path(LOG_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")
