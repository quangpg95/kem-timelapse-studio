from pathlib import Path

import pytest

from kem_timelapse.audio.pipeline import AudioPipeline
from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import (
    MediaInfo,
    Segment,
    SegmentKind,
    SourceClip,
    Timeline,
    TimelineItem,
    Variant,
)
from kem_timelapse.media.process import CompletedCommand


class FailingDenoiser:
    def process(self, input_wav: Path, output_wav: Path) -> None:
        raise RuntimeError("model unavailable")


class RecordingFallback:
    def __init__(self) -> None:
        self.called = False

    def process(self, input_wav: Path, output_wav: Path) -> None:
        self.called = True
        output_wav.write_bytes(input_wav.read_bytes())


def test_denoise_failure_uses_ffmpeg_fallback_and_warning(tmp_path: Path) -> None:
    source = tmp_path / "selected.wav"
    source.write_bytes(b"wav")
    fallback = RecordingFallback()
    pipeline = AudioPipeline(primary=FailingDenoiser(), fallback=fallback)
    result = pipeline.denoise(source, tmp_path / "clean.wav")
    assert fallback.called is True
    assert result.warning is WarningCode.AUDIO_DENOISE_DEGRADED
    assert result.path.read_bytes() == b"wav"


class CopyDenoiser:
    def __init__(self) -> None:
        self.calls = 0

    def process(self, input_wav: Path, output_wav: Path) -> None:
        self.calls += 1
        output_wav.write_bytes(input_wav.read_bytes())


class AudioRecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args: list[str], cancel_event: object | None = None) -> CompletedCommand:
        self.calls.append(args)
        Path(args[-1]).write_bytes(b"audio")
        return CompletedCommand(0, "", "")


def source_and_segment(tmp_path: Path) -> tuple[SourceClip, Segment]:
    path = tmp_path / "source.mov"
    path.write_bytes(b"video")
    source = SourceClip(
        id="source-1",
        path=path,
        size_bytes=5,
        mtime_ns=path.stat().st_mtime_ns,
        fingerprint="fingerprint",
        media=MediaInfo(
            duration_ms=10_000,
            width=3840,
            height=2160,
            fps_num=30,
            fps_den=1,
            codec="hevc",
            has_audio=True,
        ),
        order=0,
    )
    segment = Segment(
        id="segment-1",
        source_id=source.id,
        start_ms=1_000,
        end_ms=5_000,
        kind=SegmentKind.DETAIL,
        activity_score=0.8,
        detail_score=0.9,
        audio_score=0.8,
        roi_confidence=0.9,
        recommended_speed=2,
        keep_default=True,
        reason_codes=[],
    )
    return source, segment


def timeline(variant: Variant, segment: Segment, *, mode: str = "asmr") -> Timeline:
    return Timeline(
        variant=variant,
        revision=0,
        audio_mode=mode,  # type: ignore[arg-type]
        items=[
            TimelineItem(
                id=f"{variant.value}-body",
                role="body",
                segment_id=segment.id,
                trim_in_ms=1_000,
                trim_out_ms=5_000,
                speed=2,
            )
        ],
    )


def test_prepare_variant_extracts_selected_range_and_reuses_denoise_cache(
    tmp_path: Path,
) -> None:
    source, segment = source_and_segment(tmp_path)
    timelines = [
        timeline(Variant.TIKTOK_FAST, segment),
        timeline(Variant.REELS_AESTHETIC, segment),
    ]
    runner = AudioRecordingRunner()
    denoiser = CopyDenoiser()
    pipeline = AudioPipeline(primary=denoiser, fallback=denoiser, runner=runner)

    first = pipeline.prepare_variant(
        Variant.TIKTOK_FAST,
        timelines,
        {segment.id: segment},
        {source.id: source},
        tmp_path / "cache" / "audio",
        None,
        False,
    )
    second = pipeline.prepare_variant(
        Variant.REELS_AESTHETIC,
        timelines,
        {segment.id: segment},
        {source.id: source},
        tmp_path / "cache" / "audio",
        None,
        False,
    )

    assert denoiser.calls == 1
    extraction = runner.calls[0]
    assert extraction[:8] == [
        "ffmpeg", "-y", "-v", "error", "-ss", "1.000", "-i", str(source.path)
    ]
    assert ["-t", "4.000"] == extraction[8:10]
    assert all(path.stat().st_size > 0 for path in first.stem_paths)
    assert "loudnorm=I=-14:TP=-1:LRA=7" in first.filter_graph
    assert first.filter_graph.endswith("alimiter=limit=0.891:level=false[outa]")
    assert "atempo=2" in first.filter_graph
    assert first.mix_path != second.mix_path


def test_prepare_variant_rejects_unconfirmed_music_rights(tmp_path: Path) -> None:
    source, segment = source_and_segment(tmp_path)
    music = tmp_path / "music.wav"
    music.write_bytes(b"music")
    pipeline = AudioPipeline(
        primary=CopyDenoiser(), fallback=CopyDenoiser(), runner=AudioRecordingRunner()
    )

    with pytest.raises(ValueError, match="rights_confirmed"):
        pipeline.prepare_variant(
            Variant.TIKTOK_FAST,
            [timeline(Variant.TIKTOK_FAST, segment, mode="asmr_music")],
            {segment.id: segment},
            {source.id: source},
            tmp_path / "cache",
            music,
            False,
        )
