from __future__ import annotations

from collections.abc import Mapping, Sequence

from kem_timelapse.audio.models import SourceRange
from kem_timelapse.domain.models import Segment, Timeline


def merge_selected_ranges(
    ranges: Sequence[SourceRange],
    *,
    join_gap_ms: int = 0,
) -> list[SourceRange]:
    if join_gap_ms < 0:
        raise ValueError("join_gap_ms must not be negative")
    ordered = sorted(ranges, key=lambda item: (item.source_id, item.start_ms, item.end_ms))
    merged: list[SourceRange] = []
    for current in ordered:
        if (
            merged
            and merged[-1].source_id == current.source_id
            and current.start_ms <= merged[-1].end_ms + join_gap_ms
        ):
            previous = merged[-1]
            merged[-1] = SourceRange(
                source_id=previous.source_id,
                start_ms=previous.start_ms,
                end_ms=max(previous.end_ms, current.end_ms),
            )
        else:
            merged.append(current)
    return merged


def ranges_from_timelines(
    timelines: Sequence[Timeline],
    segments: Mapping[str, Segment],
    *,
    join_gap_ms: int = 0,
) -> list[SourceRange]:
    selected: dict[tuple[str, int, int], SourceRange] = {}
    for timeline in timelines:
        for item in timeline.items:
            if not item.keep:
                continue
            try:
                segment = segments[item.segment_id]
            except KeyError as error:
                raise ValueError(f"unknown segment: {item.segment_id}") from error
            if item.trim_in_ms < segment.start_ms or item.trim_out_ms > segment.end_ms:
                raise ValueError(f"timeline item outside segment range: {item.id}")
            source_range = SourceRange(
                source_id=segment.source_id,
                start_ms=item.trim_in_ms,
                end_ms=item.trim_out_ms,
            )
            selected[(source_range.source_id, source_range.start_ms, source_range.end_ms)] = (
                source_range
            )
    return merge_selected_ranges(list(selected.values()), join_gap_ms=join_gap_ms)
