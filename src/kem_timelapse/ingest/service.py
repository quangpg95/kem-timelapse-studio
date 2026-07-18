from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from kem_timelapse.domain.models import MediaInfo, SourceClip
from kem_timelapse.storage.fingerprint import fingerprint_source


class Probe(Protocol):
    def probe(self, path: Path) -> MediaInfo: ...


class IngestService:
    def __init__(self, probe: Probe) -> None:
        self._probe = probe

    def ingest(self, paths: Sequence[Path]) -> list[SourceClip]:
        resolved = [path.expanduser().resolve(strict=True) for path in paths]
        records = [(path, self._probe.probe(path), fingerprint_source(path)) for path in resolved]
        records.sort(
            key=lambda item: (
                item[1].creation_time is None,
                item[1].creation_time or "",
                item[0].name,
            )
        )
        return [
            SourceClip(
                id=f"clip-{fingerprint[:16]}",
                path=path,
                size_bytes=path.stat().st_size,
                mtime_ns=path.stat().st_mtime_ns,
                fingerprint=fingerprint,
                media=media,
                order=order,
            )
            for order, (path, media, fingerprint) in enumerate(records)
        ]
