from kem_timelapse.audio.models import SourceRange
from kem_timelapse.audio.ranges import merge_selected_ranges, ranges_from_timelines
from kem_timelapse.domain.models import Segment, SegmentKind, Timeline, TimelineItem, Variant


def test_merge_selected_ranges_unions_overlap_and_small_gaps_per_source() -> None:
    ranges = [
        SourceRange(source_id="a", start_ms=0, end_ms=1_000),
        SourceRange(source_id="a", start_ms=900, end_ms=2_000),
        SourceRange(source_id="a", start_ms=2_100, end_ms=3_000),
        SourceRange(source_id="b", start_ms=0, end_ms=500),
    ]
    assert merge_selected_ranges(ranges, join_gap_ms=100) == [
        SourceRange(source_id="a", start_ms=0, end_ms=3_000),
        SourceRange(source_id="b", start_ms=0, end_ms=500),
    ]


def test_ranges_from_timelines_deduplicates_and_validates_absolute_trims() -> None:
    segment = Segment(
        id="segment-1",
        source_id="source-1",
        start_ms=1_000,
        end_ms=4_000,
        kind=SegmentKind.DETAIL,
        activity_score=0.8,
        detail_score=0.9,
        audio_score=0.7,
        roi_confidence=0.9,
        recommended_speed=2,
        keep_default=True,
        reason_codes=[],
    )
    item = TimelineItem(
        id="item-1",
        role="body",
        segment_id=segment.id,
        trim_in_ms=1_500,
        trim_out_ms=3_500,
        speed=2,
    )
    timelines = [
        Timeline(variant=variant, revision=0, audio_mode="asmr", items=[item])
        for variant in (Variant.TIKTOK_FAST, Variant.REELS_AESTHETIC)
    ]

    assert ranges_from_timelines(timelines, {segment.id: segment}) == [
        SourceRange(source_id="source-1", start_ms=1_500, end_ms=3_500)
    ]
