from __future__ import annotations

import os
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import SourceClip
from kem_timelapse.media.process import CompletedCommand


class ProxyArtifact(BaseModel):
    source_id: str
    path: Path
    width: int
    height: int
    fps: int = 10
    duration_ms: int
    cache_key: str


class Runner(Protocol):
    def run(
        self,
        args: Sequence[str],
        cancel_event: threading.Event | None = None,
    ) -> CompletedCommand: ...


class ProxyBuilder:
    VERSION = "proxy-v1-720p10"

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def build(
        self,
        clip: SourceClip,
        cache_dir: Path,
        cancel_event: threading.Event | None,
    ) -> ProxyArtifact:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = f"{clip.fingerprint}-{self.VERSION}"
        final_path = cache_dir / f"{clip.id}-{cache_key[-18:]}.mp4"
        artifact = ProxyArtifact(
            source_id=clip.id,
            path=final_path,
            width=720 if clip.media.rotation_deg in (90, 270) else 1280,
            height=1280 if clip.media.rotation_deg in (90, 270) else 720,
            duration_ms=clip.media.duration_ms,
            cache_key=cache_key,
        )
        if final_path.is_file() and final_path.stat().st_size > 0:
            return artifact
        temporary = final_path.with_suffix(".partial.mp4")
        scale_filter = (
            "scale=720:-2,fps=10,format=yuv420p"
            if clip.media.rotation_deg in (90, 270)
            else "scale=-2:720,fps=10,format=yuv420p"
        )
        result = self._runner.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(clip.path),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                scale_filter,
                "-c:v",
                "h264_videotoolbox",
                "-b:v",
                "2M",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            cancel_event,
        )
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            raise PipelineError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "proxy generation failed",
                context={"source_id": clip.id, "stderr": result.stderr[-500:]},
            )
        os.replace(temporary, final_path)
        return artifact
