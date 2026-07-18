from __future__ import annotations

import json
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any, NoReturn, Protocol

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.media.process import CommandRunner, CompletedCommand
from kem_timelapse.render.models import OutputProbe


class ProbeRunner(Protocol):
    def run(
        self, args: Sequence[str], cancel_event: object | None = None
    ) -> CompletedCommand: ...


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _frame_rate(value: Any) -> float:
    try:
        return float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return 0.0


class OutputValidator:
    def __init__(self, runner: ProbeRunner | None = None) -> None:
        self._runner = runner or CommandRunner()

    def validate(self, path: Path) -> OutputProbe:
        violations: list[str] = []
        if not path.is_file() or path.stat().st_size == 0:
            self._raise(path, ["file"])

        result = self._runner.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ]
        )
        if result.returncode != 0:
            self._raise(path, ["ffprobe"])
        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            self._raise(path, ["ffprobe_json"])
        if not isinstance(payload, dict):
            self._raise(path, ["ffprobe_json"])

        format_info = payload.get("format", {})
        if not isinstance(format_info, dict):
            format_info = {}
        streams = payload.get("streams", [])
        if not isinstance(streams, list):
            streams = []
        video_streams = [
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ]
        audio_streams = [
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ]

        format_name = str(format_info.get("format_name", ""))
        if "mp4" not in format_name.lower() and "mov" not in format_name.lower():
            violations.append("container")
        start_time = _number(format_info.get("start_time"))
        if start_time < -0.001:
            violations.append("start_time")
        duration = _number(format_info.get("duration"))
        if duration <= 0:
            violations.append("duration")

        if len(video_streams) != 1:
            violations.append("video_stream_count")
        video: dict[str, Any] = video_streams[0] if video_streams else {}
        video_codec = str(video.get("codec_name", ""))
        width = int(_number(video.get("width")))
        height = int(_number(video.get("height")))
        pixel_format = str(video.get("pix_fmt", ""))
        fps = _frame_rate(video.get("avg_frame_rate"))
        if video_codec != "h264":
            violations.append("video_codec")
        if (width, height) != (1080, 1920):
            violations.append("dimensions")
        if pixel_format != "yuv420p":
            violations.append("pixel_format")
        if abs(fps - 30.0) > 0.01:
            violations.append("fps")

        if len(audio_streams) != 1:
            violations.append("audio_stream_count")
        audio: dict[str, Any] = audio_streams[0] if audio_streams else {}
        audio_codec = str(audio.get("codec_name", ""))
        if audio_codec != "aac":
            violations.append("audio_codec")

        if violations:
            self._raise(path, violations)
        return OutputProbe(
            path=path,
            video_codec=video_codec,
            width=width,
            height=height,
            pixel_format=pixel_format,
            fps=fps,
            audio_codec=audio_codec,
            has_aac=audio_codec == "aac",
            start_time_ms=round(start_time * 1000),
            duration_ms=round(duration * 1000),
        )

    @staticmethod
    def _raise(path: Path, violations: list[str]) -> NoReturn:
        raise PipelineError(
            ErrorCode.OUTPUT_VALIDATION_FAILED,
            "rendered output violates platform contract",
            context={"violations": violations, "filename": path.name},
        )
