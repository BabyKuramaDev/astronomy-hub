"""Write a deterministic tar.gz: sorted entries, fixed owner, mode and times."""

import gzip
import hashlib
import io
import tarfile
from pathlib import Path


def pack(root: Path, files: list[str], dest: Path) -> str:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for rel in sorted(files):
            data = (root / rel).read_bytes()
            info = tarfile.TarInfo(name=f"{root.name}/{rel}")
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    payload = gzip.compress(buffer.getvalue(), mtime=0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(dest)
    return "sha256:" + hashlib.sha256(payload).hexdigest()
