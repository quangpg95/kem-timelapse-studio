from kem_timelapse.compose.composer import compose_timeline, timeline_duration_ms
from kem_timelapse.compose.presets import REELS, SHORTS, TIKTOK
from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import Segment, SegmentKind, Variant


def segment(index: int, kind: SegmentKind, duration_ms: int, score: float) -> Segment:
    start = index * 20_000
    return Segment(
        id=f"s-{index}",
        source_id="clip-1",
        start_ms=start,
        end_ms=start + duration_ms,
        kind=kind,
        activity_score=score,
        detail_score=score,
        audio_score=score,
        roi_confidence=0.9,
        recommended_speed=2,
        keep_default=True,
        reason_codes=[kind.value],
    )


def pool() -> list[Segment]:
    kinds = [
        SegmentKind.REVEAL_CANDIDATE,
        SegmentKind.BROAD_FILL,
        SegmentKind.PROGRESS,
        SegmentKind.DETAIL,
        SegmentKind.ASMR_PEAK,
        SegmentKind.DETAIL,
        SegmentKind.PROGRESS,
        SegmentKind.REVEAL_CANDIDATE,
    ]
    return [segment(index, kind, 20_000, 0.5 + index * 0.05) for index, kind in enumerate(kinds)]


def test_all_composers_meet_duration_and_structure_contracts() -> None:
    contracts = [
        (TIKTOK, Variant.TIKTOK_FAST),
        (REELS, Variant.REELS_AESTHETIC),
        (SHORTS, Variant.SHORTS_ASMR),
    ]
    timelines = [compose_timeline(pool(), preset) for preset, _ in contracts]
    for timeline, (preset, variant) in zip(timelines, contracts, strict=True):
        assert timeline.variant is variant
        assert preset.min_ms <= timeline_duration_ms(timeline) <= preset.max_ms
        assert timeline.items[0].segment_id in {"s-0", "s-7"}
        assert timeline.items[-1].segment_id in {"s-0", "s-7"}
    assert timelines[0].model_dump() != timelines[1].model_dump()
    assert timelines[1].model_dump() != timelines[2].model_dump()


def test_composers_are_deterministic_and_platform_specific() -> None:
    source = pool()
    tiktok_a = compose_timeline(source, TIKTOK)
    tiktok_b = compose_timeline(source, TIKTOK)
    shorts = compose_timeline(source, SHORTS)
    assert tiktok_a.model_dump(mode="json") == tiktok_b.model_dump(mode="json")
    assert sum(item.speed == 12 for item in tiktok_a.items) > sum(
        item.speed == 12 for item in shorts.items
    )
    asmr_id = max(
        (item for item in source if item.kind is SegmentKind.ASMR_PEAK),
        key=lambda item: item.audio_score,
    ).id
    assert any(item.segment_id == asmr_id for item in shorts.items)


def test_inactivity_is_never_composed() -> None:
    source = pool() + [
        segment(9, SegmentKind.INACTIVE, 60_000, 1.0).model_copy(update={"keep_default": False})
    ]
    timeline = compose_timeline(source, SHORTS)
    assert "s-9" not in {item.segment_id for item in timeline.items}


def test_missing_reveal_falls_back_to_latest_kept_segment() -> None:
    source = [segment(index, SegmentKind.DETAIL, 40_000, 0.8) for index in range(4)]
    timeline = compose_timeline(source, SHORTS)
    assert timeline.items[0].segment_id == "s-3"
    assert timeline.items[-1].segment_id == "s-3"


def test_insufficient_material_has_stable_blocking_error() -> None:
    try:
        compose_timeline([segment(0, SegmentKind.DETAIL, 1_000, 0.8)], SHORTS)
    except PipelineError as error:
        assert error.code is ErrorCode.TIMELINE_INVALID
        assert error.context["variant"] == Variant.SHORTS_ASMR.value
    else:
        raise AssertionError("expected PipelineError")
