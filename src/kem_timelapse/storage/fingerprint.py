from __future__ import annotations

import hashlib
from pathlib import Path


def fingerprint_source(path: Path, chunk_bytes: int = 8_388_608) -> str:
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(f"{stat.st_size}:{stat.st_mtime_ns}:".encode())
    with path.open("rb") as stream:
        digest.update(stream.read(chunk_bytes))
        if stat.st_size > chunk_bytes:
            stream.seek(max(0, stat.st_size - chunk_bytes))
            digest.update(stream.read(chunk_bytes))
    return digest.hexdigest()
