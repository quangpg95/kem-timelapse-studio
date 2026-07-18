from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from kem_timelapse.audio.backends import FfmpegDenoiseBackend
from kem_timelapse.audio.pipeline import AudioPipeline
from kem_timelapse.domain.models import (
    MediaInfo,
    Segment,
    SegmentKind,
    SourceClip,
    Timeline,
    TimelineItem,
    Variant,
)
from kem_timelapse.media.process import CommandRunner


class FailingDenoiser:
    def process(self, input_wav: Path, output_wav: Path) -> None:
        raise RuntimeError("DeepFilterNet unavailable in integration test")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True)


@pytest.mark.media
def test_fallback_mix_meets_loudness_peak_and_duration_contract(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg and ffprobe are required")

    source = tmp_path / "asmr.wav"
    music = tmp_path / "music.wav"
    burst_gate = "+".join(
        f"between(t\\,{start:.1f}\\,{start + 0.2:.1f})"
        for start in (1.0, 2.5, 4.0, 5.5, 7.0, 8.5)
    )
    run(
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        f"aevalsrc=0.03*sin(2*PI*100*t)+0.15*sin(2*PI*6000*t)*({burst_gate}):s=48000:d=10",
        "-c:a", "pcm_s24le", str(source),
    )
    run(
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "anoisesrc=color=pink:amplitude=0.05:duration=10:r=48000",
        "-c:a", "pcm_s24le", str(music),
    )
    clip = SourceClip(
        id="source-1",
        path=source,
        size_bytes=source.stat().st_size,
        mtime_ns=source.stat().st_mtime_ns,
        fingerprint="golden-audio",
        media=MediaInfo(
            duration_ms=10_000,
            width=1920,
            height=1080,
            fps_num=30,
            fps_den=1,
            codec="pcm_s24le",
            has_audio=True,
        ),
        order=0,
    )
    segment = Segment(
        id="segment-1",
        source_id=clip.id,
        start_ms=0,
        end_ms=10_000,
        kind=SegmentKind.ASMR_PEAK,
        activity_score=0.8,
        detail_score=0.8,
        audio_score=1.0,
        roi_confidence=0.9,
        recommended_speed=1,
        keep_default=True,
        reason_codes=[],
    )
    timeline = Timeline(
        variant=Variant.TIKTOK_FAST,
        revision=0,
        audio_mode="asmr_music",
        items=[
            TimelineItem(
                id="item-1",
                role="body",
                segment_id=segment.id,
                trim_in_ms=0,
                trim_out_ms=10_000,
                speed=1,
            )
        ],
    )
    runner = CommandRunner()
    pipeline = AudioPipeline(
        primary=FailingDenoiser(),
        fallback=FfmpegDenoiseBackend(runner),
        runner=runner,
    )

    plan = pipeline.prepare_variant(
        Variant.TIKTOK_FAST,
        [timeline],
        {segment.id: segment},
        {clip.id: clip},
        tmp_path / "cache" / "audio",
        music,
        True,
    )

    measurement = run(
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(plan.mix_path),
        "-filter_complex", "ebur128=peak=true", "-f", "null", "-",
    ).stderr
    loudness = float(re.findall(r"I:\s*(-?\d+(?:\.\d+)?) LUFS", measurement)[-1])
    true_peak = float(re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?) dBFS", measurement)[-1])
    probe = json.loads(
        run(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(plan.mix_path),
        ).stdout
    )
    sample_peak_report = run(
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(plan.mix_path),
        "-af", "astats=metadata=1:reset=0", "-f", "null", "-",
    ).stderr
    sample_peaks = [
        float(value)
        for value in re.findall(r"Peak level dB:\s*(-?\d+(?:\.\d+)?)", sample_peak_report)
    ]

    assert loudness == pytest.approx(-14.0, abs=1.0)
    assert true_peak <= -0.8
    assert sample_peaks and max(sample_peaks) <= 0.0
    assert abs(float(probe["format"]["duration"]) - 10.0) < 0.05
