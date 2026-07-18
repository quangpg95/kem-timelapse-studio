from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Literal, Protocol, cast

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import MediaInfo
from kem_timelapse.media.process import CompletedCommand


class Runner(Protocol):
    def run(
        self,
        args: Sequence[str],
        cancel_event: threading.Event | None = None,
    ) -> CompletedCommand: ...


class MediaProbe:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def probe(self, path: Path) -> MediaInfo:
        result = self._runner.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ]
        )
        if result.returncode != 0:
            raise PipelineError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "ffprobe could not read source",
                context={"path": str(path), "stderr": result.stderr[-500:]},
            )
        payload = json.loads(result.stdout)
        video = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
        audio = any(stream["codec_type"] == "audio" for stream in payload["streams"])
        fps = Fraction(video.get("avg_frame_rate", "30/1"))
        rotation = 0
        for side_data in video.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = int(side_data["rotation"]) % 360
        rotation_deg = cast(Literal[0, 90, 180, 270], rotation)
        tags = payload.get("format", {}).get("tags", {})
        return MediaInfo(
            duration_ms=round(float(payload["format"]["duration"]) * 1_000),
            width=int(video["width"]),
            height=int(video["height"]),
            fps_num=fps.numerator,
            fps_den=fps.denominator,
            codec=str(video["codec_name"]),
            rotation_deg=rotation_deg,
            has_audio=audio,
            creation_time=tags.get("creation_time"),
        )
