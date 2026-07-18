from __future__ import annotations

from collections.abc import Iterable

from kem_timelapse.compose.presets import ComposerPreset
from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import Segment, SegmentKind, Timeline, TimelineItem


def timeline_duration_ms(timeline: Timeline) -> int:
    """Return the rendered duration of kept timeline items in milliseconds."""
    return round(
        sum(
            (item.trim_out_ms - item.trim_in_ms) / item.speed
            for item in timeline.items
            if item.keep
        )
    )


def compose_timeline(segments: list[Segment], preset: ComposerPreset) -> Timeline:
    """Compose a stable hook/body/reveal timeline within one platform's budget."""
    kept = [
        segment
        for segment in segments
        if segment.keep_default and segment.kind is not SegmentKind.INACTIVE
    ]
    if not kept:
        raise _duration_error(preset, 0)

    reveal = _reveal_segment(kept)
    items = [
        _reference_item(preset, "hook", reveal, preset.hook_ms, 0),
    ]
    body_candidates = _rank_candidates(kept, reveal, preset)
    body_items = _select_body_items(body_candidates, preset, items)
    items.extend(body_items)
    items.append(_reference_item(preset, "reveal", reveal, preset.reveal_ms, 0))

    _extend_to_minimum(items, body_candidates, preset)
    timeline = Timeline(
        variant=preset.variant,
        revision=0,
        audio_mode=preset.audio_mode,
        items=_renumber(items, preset),
    )
    duration_ms = timeline_duration_ms(timeline)
    if not preset.min_ms <= duration_ms <= preset.max_ms:
        raise _duration_error(preset, duration_ms)
    return timeline


def _reveal_segment(segments: list[Segment]) -> Segment:
    candidates = [segment for segment in segments if segment.kind is SegmentKind.REVEAL_CANDIDATE]
    if candidates:
        return max(candidates, key=lambda segment: _strength(segment))
    return segments[-1]


def _rank_candidates(
    kept: list[Segment],
    reveal: Segment,
    preset: ComposerPreset,
) -> list[Segment]:
    indexed = [
        (index, segment)
        for index, segment in enumerate(kept)
        if segment.id != reveal.id
    ]
    ranked = sorted(
        indexed,
        key=lambda entry: (
            -preset.score_weights.get(entry[1].kind, 0.0) * _strength(entry[1]),
            entry[0],
            entry[1].start_ms,
            entry[1].id,
        ),
    )
    return [segment for _, segment in ranked]


def _select_body_items(
    candidates: list[Segment],
    preset: ComposerPreset,
    initial_items: list[TimelineItem],
) -> list[TimelineItem]:
    selected: list[TimelineItem] = []
    reserved_reveal_ms = preset.reveal_ms
    current_ms = _items_duration(initial_items) + reserved_reveal_ms
    for segment in candidates:
        speed = preset.speed_by_kind.get(segment.kind, segment.recommended_speed)
        candidate_duration_ms = (segment.end_ms - segment.start_ms) / speed
        remaining_ms = preset.target_ms - current_ms
        if remaining_ms <= 0:
            break
        trim_out_ms = segment.end_ms
        if candidate_duration_ms > remaining_ms:
            trim_out_ms = min(segment.end_ms, segment.start_ms + round(remaining_ms * speed))
        if trim_out_ms <= segment.start_ms:
            continue
        selected.append(
            TimelineItem(
                id="pending",
                role="body",
                segment_id=segment.id,
                trim_in_ms=segment.start_ms,
                trim_out_ms=trim_out_ms,
                speed=speed,
            )
        )
        current_ms += (trim_out_ms - segment.start_ms) / speed
    return sorted(selected, key=lambda item: (item.trim_in_ms, item.trim_out_ms, item.segment_id))


def _extend_to_minimum(
    items: list[TimelineItem],
    candidates: list[Segment],
    preset: ComposerPreset,
) -> None:
    while round(_items_duration(items) + preset.reveal_ms) < preset.min_ms:
        existing = {item.segment_id for item in items if item.role == "body"}
        next_segment = next((segment for segment in candidates if segment.id not in existing), None)
        if next_segment is not None:
            speed = preset.speed_by_kind.get(next_segment.kind, next_segment.recommended_speed)
            items.append(
                TimelineItem(
                    id="pending",
                    role="body",
                    segment_id=next_segment.id,
                    trim_in_ms=next_segment.start_ms,
                    trim_out_ms=next_segment.end_ms,
                    speed=speed,
                )
            )
            continue
        if not _slow_one_body_item(items):
            return


def _slow_one_body_item(items: Iterable[TimelineItem]) -> bool:
    for item in items:
        if item.role != "body":
            continue
        if item.speed == 4:
            item.speed = 2
            return True
        if item.speed == 2:
            item.speed = 1
            return True
    return False


def _reference_item(
    preset: ComposerPreset,
    role: str,
    segment: Segment,
    duration_ms: int,
    ordinal: int,
) -> TimelineItem:
    trim_in_ms = max(segment.start_ms, segment.end_ms - duration_ms)
    return TimelineItem(
        id=f"{preset.variant.value}-{role}-{segment.id}-{ordinal}",
        role=role,  # type: ignore[arg-type]
        segment_id=segment.id,
        trim_in_ms=trim_in_ms,
        trim_out_ms=segment.end_ms,
        speed=1,
    )


def _renumber(items: list[TimelineItem], preset: ComposerPreset) -> list[TimelineItem]:
    ordinals: dict[tuple[str, str], int] = {}
    result: list[TimelineItem] = []
    for item in items:
        key = (item.role, item.segment_id)
        ordinal = ordinals.get(key, 0)
        ordinals[key] = ordinal + 1
        result.append(
            item.model_copy(
                update={"id": f"{preset.variant.value}-{item.role}-{item.segment_id}-{ordinal}"}
            )
        )
    return result


def _strength(segment: Segment) -> float:
    return max(segment.activity_score, segment.detail_score, segment.audio_score)


def _items_duration(items: Iterable[TimelineItem]) -> float:
    return sum((item.trim_out_ms - item.trim_in_ms) / item.speed for item in items if item.keep)


def _duration_error(preset: ComposerPreset, duration_ms: int) -> PipelineError:
    return PipelineError(
        ErrorCode.TIMELINE_INVALID,
        "duration outside preset",
        context={"variant": preset.variant.value, "duration_ms": duration_ms},
    )
