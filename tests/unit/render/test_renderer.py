from pathlib import Path
from threading import Event

import pytest

from kem_timelapse.audio.models import AudioMixPlan
from kem_timelapse.domain.errors import ErrorCode, PipelineError, WarningCode
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
from kem_timelapse.media.process import CompletedCommand
from kem_timelapse.render.models import OutputProbe, RenderPlan
from kem_timelapse.render.renderer import (
    Renderer,
    build_render_plan,
    output_filename,
    safe_painting_slug,
)


def test_output_names_are_ascii_and_platform_specific() -> None:
    assert safe_painting_slug("Tranh Biển 07") == "tranh-bien-07"
    assert safe_painting_slug("---") == "painting"
    assert [output_filename("Tranh Biển 07", variant) for variant in Variant] == [
        "tranh-bien-07_tiktok-fast.mp4",
        "tranh-bien-07_reels-aesthetic.mp4",
        "tranh-bien-07_shorts-asmr.mp4",
    ]


def source(path: Path) -> SourceClip:
    return SourceClip(
        id="clip-1",
        path=path,
        size_bytes=10,
        mtime_ns=1,
        fingerprint="abc",
        media=MediaInfo(
            duration_ms=5_000,
            width=3840,
            height=2160,
            fps_num=30,
            fps_den=1,
            codec="h264",
            has_audio=True,
        ),
        order=0,
    )


def segment() -> Segment:
    return Segment(
        id="s1",
        source_id="clip-1",
        start_ms=1_000,
        end_ms=5_000,
        kind=SegmentKind.DETAIL,
        activity_score=0.8,
        detail_score=0.9,
        audio_score=0.7,
        roi_confidence=0.9,
        recommended_speed=2,
        keep_default=True,
        reason_codes=["detail"],
    )


def timeline() -> Timeline:
    return Timeline(
        variant=Variant.SHORTS_ASMR,
        revision=2,
        audio_mode="asmr",
        items=[
            TimelineItem(
                id="body-s1",
                role="body",
                segment_id="s1",
                trim_in_ms=1_000,
                trim_out_ms=5_000,
                speed=2,
            )
        ],
    )


def audio(path: Path) -> AudioMixPlan:
    return AudioMixPlan(
        variant=Variant.SHORTS_ASMR,
        mode="asmr",
        stem_paths=[],
        music_path=None,
        filter_graph="",
        mix_path=path,
        warning_codes=[WarningCode.NO_SOURCE_AUDIO],
    )


def framing(*, manual: bool = False) -> FramingPlan:
    return FramingPlan(
        crop_width=1214,
        crop_height=2160,
        keyframes=[CropKeyframe(timestamp_ms=0, center_x=0.5, center_y=0.5, scale=1)],
        requires_manual_roi=manual,
        warning_codes=[],
    )


def watermark() -> WatermarkPlacement:
    return WatermarkPlacement(
        corner="bottom-left", x=0.03, y=0.747, text="@kem12032024", opacity=0.3
    )


def test_build_render_plan_has_deterministic_command_and_duration(tmp_path: Path) -> None:
    source_path = tmp_path / "source.mov"
    mix_path = tmp_path / "mix.wav"

    plan = build_render_plan(
        timeline(),
        {"s1": segment()},
        {"clip-1": source(source_path)},
        audio(mix_path),
        framing(),
        watermark(),
        tmp_path / "outputs",
        "Tranh Biển 07",
    )

    assert plan.expected_duration_ms == 2_000
    assert plan.final_path.name == "tranh-bien-07_shorts-asmr.mp4"
    assert plan.temporary_path.name == "tranh-bien-07_shorts-asmr.partial.mp4"
    assert plan.ffmpeg_args[:4] == ["ffmpeg", "-y", "-v", "error"]
    assert plan.ffmpeg_args[-1] == str(plan.temporary_path)
    assert plan.warning_codes == [WarningCode.NO_SOURCE_AUDIO]


def test_build_render_plan_blocks_unconfirmed_low_confidence_roi(tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as caught:
        build_render_plan(
            timeline(),
            {"s1": segment()},
            {"clip-1": source(tmp_path / "source.mov")},
            audio(tmp_path / "mix.wav"),
            framing(manual=True),
            watermark(),
            tmp_path,
            "painting",
        )

    assert caught.value.code is ErrorCode.TIMELINE_INVALID


class FakeRenderRunner:
    def __init__(self, result: CompletedCommand, *, interrupt: bool = False) -> None:
        self.result = result
        self.interrupt = interrupt

    def run(self, args: list[str], cancel_event: object | None = None) -> CompletedCommand:
        output = Path(args[-1])
        output.write_bytes(b"partial")
        if self.interrupt:
            raise InterruptedError("cancelled")
        return self.result


class FakeValidator:
    def validate(self, path: Path) -> OutputProbe:
        return OutputProbe(
            path=path,
            video_codec="h264",
            width=1080,
            height=1920,
            pixel_format="yuv420p",
            fps=30,
            audio_codec="aac",
            has_aac=True,
            start_time_ms=0,
            duration_ms=2_000,
        )


def render_plan(tmp_path: Path) -> RenderPlan:
    final = tmp_path / "painting.mp4"
    return RenderPlan(
        variant=Variant.SHORTS_ASMR,
        source_paths=[tmp_path / "source.mov"],
        audio_mix_path=tmp_path / "mix.wav",
        video_filter_graph="null[vout]",
        ffmpeg_args=["ffmpeg", str(final.with_name("painting.partial.mp4"))],
        final_path=final,
        temporary_path=final.with_name("painting.partial.mp4"),
        expected_duration_ms=2_000,
        warning_codes=[],
    )


def test_renderer_validates_partial_then_atomically_promotes_it(tmp_path: Path) -> None:
    plan = render_plan(tmp_path)
    renderer = Renderer(FakeRenderRunner(CompletedCommand(0, "", "")), FakeValidator())

    probe = renderer.render(plan, Event())

    assert probe.path == plan.final_path
    assert plan.final_path.read_bytes() == b"partial"
    assert not plan.temporary_path.exists()


def test_renderer_preserves_existing_output_without_overwrite(tmp_path: Path) -> None:
    plan = render_plan(tmp_path)
    plan.final_path.write_bytes(b"existing")
    renderer = Renderer(FakeRenderRunner(CompletedCommand(0, "", "")), FakeValidator())

    with pytest.raises(PipelineError) as caught:
        renderer.render(plan, Event())

    assert caught.value.code is ErrorCode.OUTPUT_NOT_WRITABLE
    assert plan.final_path.read_bytes() == b"existing"


def test_renderer_removes_partial_on_cancellation(tmp_path: Path) -> None:
    plan = render_plan(tmp_path)
    renderer = Renderer(
        FakeRenderRunner(CompletedCommand(0, "", ""), interrupt=True), FakeValidator()
    )

    with pytest.raises(InterruptedError):
        renderer.render(plan, Event())

    assert not plan.temporary_path.exists()


def test_renderer_redacts_failed_command_to_stderr_tail(tmp_path: Path) -> None:
    plan = render_plan(tmp_path)
    stderr = "secret-prefix" + "x" * 1_100
    renderer = Renderer(FakeRenderRunner(CompletedCommand(1, "", stderr)), FakeValidator())

    with pytest.raises(PipelineError) as caught:
        renderer.render(plan, Event())

    assert caught.value.code is ErrorCode.OUTPUT_VALIDATION_FAILED
    assert caught.value.context == {"stderr_tail": stderr[-1_000:]}
    assert "secret-prefix" not in caught.value.context["stderr_tail"]
    assert not plan.temporary_path.exists()
