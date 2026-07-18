from __future__ import annotations

import os
import re
import threading
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from kem_timelapse.audio.models import AudioMixPlan
from kem_timelapse.domain.errors import ErrorCode, PipelineError, WarningCode
from kem_timelapse.domain.models import Segment, SourceClip, Timeline, Variant
from kem_timelapse.framing.models import CropKeyframe, FramingPlan, WatermarkPlacement
from kem_timelapse.media.process import CommandRunner, CompletedCommand
from kem_timelapse.render.filtergraph import CropExpression, build_video_filtergraph
from kem_timelapse.render.models import OutputProbe, RenderPlan
from kem_timelapse.render.validator import OutputValidator


class RenderRunner(Protocol):
    def run(
        self, args: Sequence[str], cancel_event: object | None = None
    ) -> CompletedCommand: ...


class Validator(Protocol):
    def validate(self, path: Path) -> OutputProbe: ...


def _timeline_invalid(reason: str) -> PipelineError:
    return PipelineError(
        ErrorCode.TIMELINE_INVALID,
        "timeline cannot be rendered",
        context={"reason": reason},
    )


def safe_painting_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character) and character.isascii()
    ).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or "painting"


def output_filename(painting_slug: str, variant: Variant) -> str:
    return f"{safe_painting_slug(painting_slug)}_{variant.value}.mp4"


def _nearest_keyframe(keyframes: Sequence[CropKeyframe], timestamp_ms: int) -> CropKeyframe:
    if not keyframes:
        raise _timeline_invalid("framing plan has no crop keyframes")
    return min(keyframes, key=lambda keyframe: abs(keyframe.timestamp_ms - timestamp_ms))


def _even(value: float) -> int:
    integer = max(2, round(value))
    return integer if integer % 2 == 0 else integer - 1


def _crop_expression(
    segment: Segment,
    source: SourceClip,
    framing: FramingPlan,
) -> CropExpression:
    keyframe = _nearest_keyframe(framing.keyframes, segment.start_ms)
    width = min(source.media.width, _even(framing.crop_width / keyframe.scale))
    height = min(source.media.height, _even(framing.crop_height / keyframe.scale))
    x = round(keyframe.center_x * source.media.width - width / 2)
    y = round(keyframe.center_y * source.media.height - height / 2)
    x = min(max(0, x), source.media.width - width)
    y = min(max(0, y), source.media.height - height)
    return str(width), str(height), str(x), str(y)


def _unique_warnings(*groups: Sequence[WarningCode]) -> list[WarningCode]:
    return list(dict.fromkeys(warning for group in groups for warning in group))


def build_render_plan(
    timeline: Timeline,
    segments: Mapping[str, Segment],
    sources: Mapping[str, SourceClip],
    audio: AudioMixPlan,
    framing: FramingPlan,
    watermark: WatermarkPlacement,
    output_dir: Path,
    painting_slug: str,
) -> RenderPlan:
    kept_items = [item for item in timeline.items if item.keep]
    if not kept_items:
        raise _timeline_invalid("timeline has no kept items")
    if audio.variant is not timeline.variant or audio.mode != timeline.audio_mode:
        raise _timeline_invalid("audio mix does not match timeline")
    if framing.requires_manual_roi:
        raise _timeline_invalid("manual ROI confirmation is required")

    used_source_ids: set[str] = set()
    crop_expressions: dict[str, CropExpression] = {}
    for item in kept_items:
        try:
            segment = segments[item.segment_id]
        except KeyError as error:
            raise _timeline_invalid(f"missing segment: {item.segment_id}") from error
        try:
            source = sources[segment.source_id]
        except KeyError as error:
            raise _timeline_invalid(f"missing source: {segment.source_id}") from error
        used_source_ids.add(source.id)
        crop_expressions[segment.id] = _crop_expression(segment, source, framing)

    ordered_sources = sorted(
        (sources[source_id] for source_id in used_source_ids),
        key=lambda source: (source.order, source.id),
    )
    input_indexes = {source.id: index for index, source in enumerate(ordered_sources)}
    video_filtergraph = build_video_filtergraph(
        timeline,
        segments,
        input_indexes,
        crop_expressions,
        watermark,
    )
    expected_duration_ms = round(
        sum((item.trim_out_ms - item.trim_in_ms) / item.speed for item in kept_items)
    )
    if expected_duration_ms <= 0:
        raise _timeline_invalid("timeline duration is not positive")

    final_path = output_dir / output_filename(painting_slug, timeline.variant)
    temporary_path = final_path.with_name(f"{final_path.stem}.partial{final_path.suffix}")
    args = ["ffmpeg", "-y", "-v", "error"]
    for source in ordered_sources:
        args.extend(["-i", str(source.path)])
    args.extend(
        [
            "-i",
            str(audio.mix_path),
            "-filter_complex",
            video_filtergraph,
            "-map",
            "[vout]",
            "-map",
            f"{len(ordered_sources)}:a:0",
            "-c:v",
            "h264_videotoolbox",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-t",
            f"{expected_duration_ms / 1000:.6f}",
            "-movflags",
            "+faststart",
            str(temporary_path),
        ]
    )
    watermark_warnings = [watermark.warning] if watermark.warning is not None else []
    return RenderPlan(
        variant=timeline.variant,
        source_paths=[source.path for source in ordered_sources],
        audio_mix_path=audio.mix_path,
        video_filter_graph=video_filtergraph,
        ffmpeg_args=args,
        final_path=final_path,
        temporary_path=temporary_path,
        expected_duration_ms=expected_duration_ms,
        warning_codes=_unique_warnings(
            audio.warning_codes,
            framing.warning_codes,
            watermark_warnings,
        ),
    )


class Renderer:
    def __init__(
        self,
        runner: RenderRunner | None = None,
        validator: Validator | None = None,
    ) -> None:
        self._runner = runner or CommandRunner()
        self._validator = validator or OutputValidator()

    def render(
        self,
        plan: RenderPlan,
        cancel_event: threading.Event,
        overwrite: bool = False,
    ) -> OutputProbe:
        if plan.final_path.exists() and not overwrite:
            raise PipelineError(
                ErrorCode.OUTPUT_NOT_WRITABLE,
                "output already exists",
                context={"filename": plan.final_path.name},
            )
        plan.final_path.parent.mkdir(parents=True, exist_ok=True)
        plan.temporary_path.unlink(missing_ok=True)
        if cancel_event.is_set():
            raise InterruptedError("render cancelled")
        try:
            result = self._runner.run(plan.ffmpeg_args, cancel_event)
            if result.returncode != 0:
                raise PipelineError(
                    ErrorCode.OUTPUT_VALIDATION_FAILED,
                    "render command failed",
                    context={"stderr_tail": result.stderr[-1_000:]},
                )
            probe = self._validator.validate(plan.temporary_path)
            os.replace(plan.temporary_path, plan.final_path)
            return probe.model_copy(update={"path": plan.final_path})
        except Exception:
            plan.temporary_path.unlink(missing_ok=True)
            raise
