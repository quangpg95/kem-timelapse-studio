from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
from statistics import fmean

from kem_timelapse.analysis.presets import AnalysisPreset
from kem_timelapse.domain.models import FeatureWindow, Segment, SegmentKind, Speed


@dataclass
class _WindowState:
    window: FeatureWindow
    activity: float
    active: bool


@dataclass
class _SegmentGroup:
    source_id: str
    start_ms: int
    end_ms: int
    kind: SegmentKind
    windows: list[FeatureWindow] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)

    @property
    def keep(self) -> bool:
        return self.kind is not SegmentKind.INACTIVE


def segment_windows(
    windows: list[FeatureWindow],
    preset: AnalysisPreset,
) -> list[Segment]:
    """Convert ordered analysis windows into deterministic, explainable segments."""
    if not windows:
        return []

    states = _hysteresis_states(windows, preset)
    state_groups = _group_activity_states(states)
    _promote_short_inactive_groups(state_groups, preset)
    groups = _classify_groups(state_groups, preset)
    groups = _bridge_equal_kinds(groups, preset)
    _mark_reveal_candidate(groups, windows, preset)
    _add_handles(groups, preset)
    return [_to_segment(group) for group in groups]


def _hysteresis_states(
    windows: list[FeatureWindow],
    preset: AnalysisPreset,
) -> list[_WindowState]:
    states: list[_WindowState] = []
    active = False
    for window in windows:
        activity = _activity(window)
        if active:
            active = activity >= preset.active_exit
        else:
            active = activity >= preset.active_enter
        states.append(_WindowState(window=window, activity=activity, active=active))
    return states


def _group_activity_states(states: list[_WindowState]) -> list[list[_WindowState]]:
    groups: list[list[_WindowState]] = []
    for state in states:
        if (
            not groups
            or groups[-1][-1].active != state.active
            or groups[-1][-1].window.source_id != state.window.source_id
        ):
            groups.append([state])
        else:
            groups[-1].append(state)
    return groups


def _promote_short_inactive_groups(
    groups: list[list[_WindowState]],
    preset: AnalysisPreset,
) -> None:
    for group in groups:
        duration_ms = group[-1].window.end_ms - group[0].window.start_ms
        if not group[0].active and duration_ms < preset.minimum_inactive_ms:
            for state in group:
                state.active = True


def _classify_groups(
    state_groups: list[list[_WindowState]],
    preset: AnalysisPreset,
) -> list[_SegmentGroup]:
    result: list[_SegmentGroup] = []
    for state_group in state_groups:
        if not state_group[0].active:
            windows = [state.window for state in state_group]
            _append_group(
                result,
                _SegmentGroup(
                    source_id=windows[0].source_id,
                    start_ms=windows[0].start_ms,
                    end_ms=windows[-1].end_ms,
                    kind=SegmentKind.INACTIVE,
                    windows=windows,
                    reason_codes=[_inactive_reason(state_group, preset)],
                ),
            )
            continue

        was_promoted = all(state.activity < preset.active_enter for state in state_group)
        for state in state_group:
            kind, reason = _classify_window(state, preset, was_promoted=was_promoted)
            _append_group(
                result,
                _SegmentGroup(
                    source_id=state.window.source_id,
                    start_ms=state.window.start_ms,
                    end_ms=state.window.end_ms,
                    kind=kind,
                    windows=[state.window],
                    reason_codes=[reason],
                ),
            )
    return result


def _classify_window(
    state: _WindowState,
    preset: AnalysisPreset,
    *,
    was_promoted: bool,
) -> tuple[SegmentKind, str]:
    window = state.window
    if window.audio_score >= preset.asmr_score:
        return SegmentKind.ASMR_PEAK, f"audio_ge_{_threshold(preset.asmr_score)}"
    if window.detail_score >= preset.detail_score:
        return SegmentKind.DETAIL, f"detail_ge_{_threshold(preset.detail_score)}"
    if window.changed_area_score >= preset.broad_area:
        return SegmentKind.BROAD_FILL, f"changed_area_ge_{_threshold(preset.broad_area)}"
    if was_promoted:
        return (
            SegmentKind.PROGRESS,
            f"inactive_duration_lt_{preset.minimum_inactive_ms}",
        )
    return SegmentKind.PROGRESS, f"activity_ge_{_threshold(preset.active_enter)}"


def _append_group(groups: list[_SegmentGroup], candidate: _SegmentGroup) -> None:
    if (
        groups
        and groups[-1].source_id == candidate.source_id
        and groups[-1].kind is candidate.kind
        and groups[-1].end_ms == candidate.start_ms
    ):
        current = groups[-1]
        current.end_ms = candidate.end_ms
        current.windows.extend(candidate.windows)
        current.reason_codes = _unique(current.reason_codes + candidate.reason_codes)
        return
    groups.append(candidate)


def _bridge_equal_kinds(
    groups: list[_SegmentGroup],
    preset: AnalysisPreset,
) -> list[_SegmentGroup]:
    result = list(groups)
    index = 0
    while index < len(result):
        right_index = index + 2
        while right_index < len(result):
            gap_ms = result[right_index].start_ms - result[index].end_ms
            if gap_ms > preset.merge_gap_ms:
                break
            if (
                result[index].source_id == result[right_index].source_id
                and result[index].kind is result[right_index].kind
            ):
                bridged = result[index : right_index + 1]
                result[index] = _SegmentGroup(
                    source_id=bridged[0].source_id,
                    start_ms=bridged[0].start_ms,
                    end_ms=bridged[-1].end_ms,
                    kind=bridged[0].kind,
                    windows=[window for group in bridged for window in group.windows],
                    reason_codes=_unique(
                        [reason for group in bridged for reason in group.reason_codes]
                        + [f"bridged_gap_le_{preset.merge_gap_ms}"]
                    ),
                )
                del result[index + 1 : right_index + 1]
                right_index = index + 2
                continue
            right_index += 1
        index += 1
    return result


def _mark_reveal_candidate(
    groups: list[_SegmentGroup],
    windows: list[FeatureWindow],
    preset: AnalysisPreset,
) -> None:
    final_group = next((group for group in reversed(groups) if group.keep), None)
    if final_group is None:
        return
    final_second_start = final_group.end_ms - 1_000
    final_windows = [window for window in final_group.windows if window.end_ms > final_second_start]
    if not final_windows:
        return
    mean_motion = fmean(window.motion_score for window in final_windows)
    mean_canvas_change = fmean(window.canvas_change_score for window in final_windows)
    first_canvas_change = windows[0].canvas_change_score
    if (
        mean_motion < preset.active_exit
        and mean_canvas_change >= preset.broad_area
        and mean_canvas_change > first_canvas_change
    ):
        original_kind = final_group.kind
        final_group.kind = SegmentKind.REVEAL_CANDIDATE
        final_group.reason_codes = _unique(
            final_group.reason_codes
            + [
                f"original_kind={original_kind.value}",
                "final_low_motion_high_canvas_change",
            ]
        )


def _add_handles(groups: list[_SegmentGroup], preset: AnalysisPreset) -> None:
    source_bounds: dict[str, tuple[int, int]] = {}
    for group in groups:
        existing = source_bounds.get(group.source_id)
        if existing is None:
            source_bounds[group.source_id] = (group.start_ms, group.end_ms)
        else:
            source_bounds[group.source_id] = (
                min(existing[0], group.start_ms),
                max(existing[1], group.end_ms),
            )

    original_bounds = [(group.start_ms, group.end_ms) for group in groups]
    for group in groups:
        if not group.keep:
            continue
        source_start, source_end = source_bounds[group.source_id]
        group.start_ms = max(source_start, group.start_ms - preset.handle_ms)
        group.end_ms = min(source_end, group.end_ms + preset.handle_ms)

    for index, (left, right) in enumerate(zip(groups, groups[1:], strict=False)):
        if left.source_id != right.source_id or left.end_ms <= right.start_ms:
            continue
        left_original_end = original_bounds[index][1]
        right_original_start = original_bounds[index + 1][0]
        if left.keep and not right.keep:
            boundary = left.end_ms
        elif not left.keep and right.keep:
            boundary = right.start_ms
        else:
            boundary = (left_original_end + right_original_start) // 2
        left.end_ms = boundary
        right.start_ms = boundary


def _to_segment(group: _SegmentGroup) -> Segment:
    activity_score = max(_activity(window) for window in group.windows)
    detail_score = max(window.detail_score for window in group.windows)
    audio_score = max(window.audio_score for window in group.windows)
    confidences = [window.roi.confidence for window in group.windows if window.roi is not None]
    roi_confidence = fmean(confidences) if confidences else 0.0
    identifier = sha1(
        f"{group.source_id}:{group.start_ms}:{group.end_ms}:{group.kind.value}".encode()
    ).hexdigest()[:16]
    return Segment(
        id=identifier,
        source_id=group.source_id,
        start_ms=group.start_ms,
        end_ms=group.end_ms,
        kind=group.kind,
        activity_score=activity_score,
        detail_score=detail_score,
        audio_score=audio_score,
        roi_confidence=roi_confidence,
        recommended_speed=_speed(group.kind),
        keep_default=group.keep,
        reason_codes=group.reason_codes,
    )


def _activity(window: FeatureWindow) -> float:
    return max(
        window.motion_score,
        window.canvas_change_score,
        window.detail_score,
        window.audio_score,
    )


def _inactive_reason(states: list[_WindowState], preset: AnalysisPreset) -> str:
    if max(state.activity for state in states) < preset.active_exit:
        return "activity_below_exit"
    return "activity_below_enter"


def _speed(kind: SegmentKind) -> Speed:
    speed_by_kind: dict[SegmentKind, Speed] = {
        SegmentKind.INACTIVE: 12,
        SegmentKind.BROAD_FILL: 12,
        SegmentKind.PROGRESS: 4,
        SegmentKind.DETAIL: 2,
        SegmentKind.ASMR_PEAK: 1,
        SegmentKind.HOOK_CANDIDATE: 1,
        SegmentKind.REVEAL_CANDIDATE: 1,
    }
    return speed_by_kind[kind]


def _threshold(value: float) -> str:
    return format(value, "g")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
