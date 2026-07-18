from __future__ import annotations

import math
from collections.abc import Mapping

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import Segment, Timeline
from kem_timelapse.framing.models import WatermarkPlacement

CropExpression = tuple[str, str, str, str]


def _timeline_invalid(reason: str) -> PipelineError:
    return PipelineError(
        ErrorCode.TIMELINE_INVALID,
        "timeline cannot be rendered",
        context={"reason": reason},
    )


def _seconds(milliseconds: int) -> str:
    return f"{milliseconds / 1000:g}"


def _escape_drawtext(value: str) -> str:
    if not value or len(value) > 100 or any(ord(character) < 32 for character in value):
        raise _timeline_invalid("unsafe watermark text")
    escaped = value.replace("\\", "\\\\")
    for character in (":", "'", "%", "[", "]"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def _default_watermark(timeline: Timeline) -> WatermarkPlacement:
    return WatermarkPlacement(
        corner="bottom-left",
        x=0.03,
        y=0.747,
        text=timeline.watermark_text,
        opacity=timeline.watermark_opacity,
    )


def build_video_filtergraph(
    timeline: Timeline,
    segments: Mapping[str, Segment],
    input_indexes: Mapping[str, int],
    crop_expressions: Mapping[str, CropExpression],
    watermark: WatermarkPlacement | None = None,
) -> str:
    """Build a deterministic video-only graph ending at ``[vout]``."""
    kept_items = [item for item in timeline.items if item.keep]
    if not kept_items:
        raise _timeline_invalid("timeline has no kept items")
    if any(not isinstance(index, int) or index < 0 for index in input_indexes.values()):
        raise _timeline_invalid("source input index is invalid")
    if len(set(input_indexes.values())) != len(input_indexes):
        raise _timeline_invalid("source input indexes must be unique")

    chains: list[str] = []
    labels: list[str] = []
    for item_index, item in enumerate(kept_items):
        try:
            segment = segments[item.segment_id]
        except KeyError as error:
            raise _timeline_invalid(f"missing segment: {item.segment_id}") from error
        try:
            input_index = input_indexes[segment.source_id]
        except KeyError as error:
            raise _timeline_invalid(f"missing source index: {segment.source_id}") from error
        try:
            crop_width, crop_height, crop_x, crop_y = crop_expressions[segment.id]
        except KeyError as error:
            raise _timeline_invalid(f"missing crop expression: {segment.id}") from error
        if not all((crop_width, crop_height, crop_x, crop_y)):
            raise _timeline_invalid(f"empty crop expression: {segment.id}")

        label = f"v{item_index}"
        chains.append(
            f"[{input_index}:v]trim=start={_seconds(item.trim_in_ms)}:"
            f"end={_seconds(item.trim_out_ms)},"
            f"setpts=(PTS-STARTPTS)/{item.speed},"
            f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y},"
            "scale=1080:1920:flags=lanczos,setsar=1,fps=30,format=yuv420p"
            f"[{label}]"
        )
        labels.append(f"[{label}]")

    chains.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[joined]")
    placement = watermark or _default_watermark(timeline)
    text = _escape_drawtext(placement.text)
    opacity = f"{placement.opacity:g}"
    if not math.isfinite(placement.x) or not math.isfinite(placement.y):
        raise _timeline_invalid("watermark position is invalid")
    chains.append(
        "[joined]drawtext="
        f"text='{text}':fontcolor=white@{opacity}:fontsize=h/32:"
        f"x=w*{placement.x:g}:y=h*{placement.y:g}[vout]"
    )
    return ";".join(chains)
