import pytest

from kem_timelapse.analysis.presets import BOOTSTRAP_PRESET
from kem_timelapse.analysis.segmenter import segment_windows
from kem_timelapse.domain.models import FeatureWindow, SegmentKind


def window(
    start: int,
    *,
    motion: float,
    area: float,
    detail: float,
    audio: float = 0.0,
) -> FeatureWindow:
    return FeatureWindow(
        source_id="clip-1",
        start_ms=start,
        end_ms=start + 500,
        motion_score=motion,
        canvas_change_score=area,
        changed_area_score=area,
        detail_score=detail,
        audio_score=audio,
    )


def inactive_window(end_ms: int) -> FeatureWindow:
    return FeatureWindow(
        source_id="clip-1",
        start_ms=0,
        end_ms=end_ms,
        motion_score=0.01,
        canvas_change_score=0.01,
        changed_area_score=0.01,
        detail_score=0.01,
        audio_score=0.01,
    )


def ranged_window(start_ms: int, end_ms: int, *, detail: float) -> FeatureWindow:
    return FeatureWindow(
        source_id="clip-1",
        start_ms=start_ms,
        end_ms=end_ms,
        motion_score=0.20 if detail else 0.01,
        canvas_change_score=0.05,
        changed_area_score=0.05,
        detail_score=detail,
        audio_score=0.0,
    )


def test_segmenter_removes_long_static_but_keeps_detail_and_asmr() -> None:
    windows = [window(i * 500, motion=0.01, area=0.01, detail=0.01) for i in range(4)]
    windows += [window(2_000, motion=0.20, area=0.08, detail=0.70)]
    windows += [window(2_500, motion=0.16, area=0.05, detail=0.25, audio=0.80)]

    segments = segment_windows(windows, BOOTSTRAP_PRESET)

    assert segments[0].kind is SegmentKind.INACTIVE
    assert segments[0].keep_default is False
    assert any(segment.kind is SegmentKind.DETAIL for segment in segments)
    assert any(segment.kind is SegmentKind.ASMR_PEAK for segment in segments)
    assert all(segment.start_ms >= 0 for segment in segments)


@pytest.mark.parametrize(("duration_ms", "deleted"), [(1_499, False), (1_500, True)])
def test_inactivity_threshold_is_inclusive(duration_ms: int, deleted: bool) -> None:
    result = segment_windows([inactive_window(duration_ms)], BOOTSTRAP_PRESET)

    assert (result[0].kind is SegmentKind.INACTIVE and not result[0].keep_default) is deleted


def test_output_is_deterministic_non_overlapping_and_clamped() -> None:
    windows = [inactive_window(1_500), window(1_500, motion=0.3, area=0.4, detail=0.1)]

    first = segment_windows(windows, BOOTSTRAP_PRESET)
    second = segment_windows(windows, BOOTSTRAP_PRESET)

    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].start_ms == 0
    assert all(
        left.end_ms <= right.start_ms
        for left, right in zip(first, first[1:], strict=False)
    )


@pytest.mark.parametrize(("gap_ms", "detail_segment_count"), [(500, 1), (501, 2)])
def test_equal_kinds_bridge_only_through_configured_gap(
    gap_ms: int,
    detail_segment_count: int,
) -> None:
    windows = [
        ranged_window(0, 1_000, detail=0.7),
        ranged_window(1_000, 1_000 + gap_ms, detail=0.0),
        ranged_window(1_000 + gap_ms, 2_000 + gap_ms, detail=0.7),
    ]

    result = segment_windows(windows, BOOTSTRAP_PRESET)

    assert sum(item.kind is SegmentKind.DETAIL for item in result) == detail_segment_count


def test_segment_kinds_have_explainable_reasons_and_default_speeds() -> None:
    windows = [
        FeatureWindow(
            source_id="clip-1",
            start_ms=0,
            end_ms=1_500,
            motion_score=0.01,
            canvas_change_score=0.01,
            changed_area_score=0.01,
            detail_score=0.01,
            audio_score=0.01,
        ),
        window(1_500, motion=0.5, area=0.4, detail=0.1),
        window(2_000, motion=0.2, area=0.1, detail=0.1),
        window(2_500, motion=0.2, area=0.1, detail=0.3),
        window(3_000, motion=0.2, area=0.1, detail=0.3, audio=0.8),
    ]

    result = segment_windows(windows, BOOTSTRAP_PRESET)
    by_kind = {segment.kind: segment for segment in result}

    assert by_kind[SegmentKind.INACTIVE].recommended_speed == 12
    assert by_kind[SegmentKind.BROAD_FILL].recommended_speed == 12
    assert by_kind[SegmentKind.PROGRESS].recommended_speed == 4
    assert by_kind[SegmentKind.DETAIL].recommended_speed == 2
    assert by_kind[SegmentKind.ASMR_PEAK].recommended_speed == 1
    assert "activity_below_exit" in by_kind[SegmentKind.INACTIVE].reason_codes
    assert "changed_area_ge_0.35" in by_kind[SegmentKind.BROAD_FILL].reason_codes
    assert "activity_ge_0.12" in by_kind[SegmentKind.PROGRESS].reason_codes
    assert "detail_ge_0.18" in by_kind[SegmentKind.DETAIL].reason_codes
    assert "audio_ge_0.55" in by_kind[SegmentKind.ASMR_PEAK].reason_codes


def test_final_low_motion_changed_canvas_becomes_reveal_candidate() -> None:
    windows = [
        window(0, motion=0.3, area=0.10, detail=0.1),
        window(500, motion=0.2, area=0.20, detail=0.1),
        window(1_000, motion=0.02, area=0.60, detail=0.1),
        window(1_500, motion=0.02, area=0.60, detail=0.1),
    ]

    result = segment_windows(windows, BOOTSTRAP_PRESET)

    assert result[-1].kind is SegmentKind.REVEAL_CANDIDATE
    assert result[-1].recommended_speed == 1
    assert "original_kind=broad_fill" in result[-1].reason_codes
    assert "final_low_motion_high_canvas_change" in result[-1].reason_codes
