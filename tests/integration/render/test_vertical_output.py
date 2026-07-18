from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from kem_timelapse.audio.models import AudioMixPlan
from kem_timelapse.domain.models import (
    MediaInfo,
    Segment,
    SegmentKind,
    SourceClip,
    Timeline,
    TimelineItem,
    Variant,
)
from kem_timelapse.framing.models import CropKeyframe, FramingPlan, WatermarkPlacement
from kem_timelapse.render.renderer import Renderer, build_render_plan
from kem_timelapse.render.validator import OutputValidator


def _ffmpeg_capability(section: str, name: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", section],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and name in result.stdout


def _require_render_backend() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg and ffprobe are required")
    if not _ffmpeg_capability("-encoders", "h264_videotoolbox"):
        pytest.skip("h264_videotoolbox encoder is unavailable")
    if not _ffmpeg_capability("-filters", "drawtext"):
        pytest.skip("FFmpeg drawtext filter is unavailable")


def _run(*args: str) -> None:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr[-1_000:]


def _make_source(path: Path, color: str, frequency: int) -> None:
    _run(
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=640x360:r=30:d=2",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frequency}:sample_rate=48000:duration=2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    )


def _make_silent_mix(path: Path, duration_seconds: float) -> None:
    _run(
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=48000:cl=stereo:d={duration_seconds}",
        "-c:a",
        "pcm_s24le",
        str(path),
    )


def _source(source_id: str, path: Path, order: int) -> SourceClip:
    stat = path.stat()
    return SourceClip(
        id=source_id,
        path=path,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        fingerprint=f"fingerprint-{source_id}",
        media=MediaInfo(
            duration_ms=2_000,
            width=640,
            height=360,
            fps_num=30,
            fps_den=1,
            codec="h264",
            has_audio=True,
        ),
        order=order,
    )


def _segment(
    segment_id: str, source_id: str, start_ms: int, end_ms: int, speed: int
) -> Segment:
    return Segment.model_validate(
        {
            "id": segment_id,
            "source_id": source_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "kind": SegmentKind.PROGRESS,
            "activity_score": 0.8,
            "detail_score": 0.6,
            "audio_score": 0.5,
            "roi_confidence": 0.9,
            "recommended_speed": speed,
            "keep_default": True,
            "reason_codes": ["integration"],
        }
    )


def _decoded_mean(path: Path, timestamp: float) -> float:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-1_000:]
    assert result.stdout
    return float(np.frombuffer(result.stdout, dtype=np.uint8).mean())


def _packet_endpoints(path: Path, selector: str) -> tuple[float, float]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            selector,
            "-show_packets",
            "-show_entries",
            "packet=pts_time",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-1_000:]
    packets = json.loads(result.stdout)["packets"]
    points = [float(packet["pts_time"]) for packet in packets if "pts_time" in packet]
    assert points
    return points[0], points[-1]


@pytest.mark.media
def test_real_vertical_output_has_clean_joins_and_synced_pts(tmp_path: Path) -> None:
    _require_render_backend()
    red = tmp_path / "red.mp4"
    blue = tmp_path / "blue.mp4"
    mix = tmp_path / "silent.wav"
    _make_source(red, "red", 440)
    _make_source(blue, "blue", 880)
    _make_silent_mix(mix, 1.3)

    segments = {
        "s1": _segment("s1", "clip-red", 0, 600, 1),
        "s2": _segment("s2", "clip-blue", 0, 1_200, 2),
        "s3": _segment("s3", "clip-red", 600, 1_800, 12),
    }
    timeline = Timeline(
        variant=Variant.SHORTS_ASMR,
        revision=0,
        audio_mode="silent",
        items=[
            TimelineItem(
                id="hook", role="hook", segment_id="s1", trim_in_ms=0, trim_out_ms=600, speed=1
            ),
            TimelineItem(
                id="body", role="body", segment_id="s2", trim_in_ms=0, trim_out_ms=1_200, speed=2
            ),
            TimelineItem(
                id="reveal",
                role="reveal",
                segment_id="s3",
                trim_in_ms=600,
                trim_out_ms=1_800,
                speed=12,
            ),
        ],
    )
    plan = build_render_plan(
        timeline,
        segments,
        {"clip-red": _source("clip-red", red, 0), "clip-blue": _source("clip-blue", blue, 1)},
        AudioMixPlan(
            variant=Variant.SHORTS_ASMR,
            mode="silent",
            stem_paths=[],
            music_path=None,
            filter_graph="",
            mix_path=mix,
            warning_codes=[],
        ),
        FramingPlan(
            crop_width=202,
            crop_height=360,
            keyframes=[CropKeyframe(timestamp_ms=0, center_x=0.5, center_y=0.5, scale=1)],
            requires_manual_roi=False,
            warning_codes=[],
        ),
        WatermarkPlacement(
            corner="bottom-left", x=0.03, y=0.747, text="@kem12032024", opacity=0.3
        ),
        tmp_path / "outputs",
        "Integration Painting",
    )

    probe = Renderer().render(plan, Event())
    validated = OutputValidator().validate(probe.path)

    assert (validated.width, validated.height, validated.fps) == (1080, 1920, 30.0)
    assert validated.has_aac is True
    for timestamp in (0.55, 0.65, 1.15, 1.25):
        assert _decoded_mean(probe.path, timestamp) > 10.0
    video_start, video_end = _packet_endpoints(probe.path, "v:0")
    audio_start, audio_end = _packet_endpoints(probe.path, "a:0")
    assert abs(video_start - audio_start) < 0.1
    assert abs(video_end - audio_end) < 0.1
