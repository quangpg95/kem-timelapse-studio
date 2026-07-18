from pathlib import Path

import pytest
from pydantic import ValidationError

from kem_timelapse.domain.models import Segment, SegmentKind, Timeline, TimelineItem, Variant


def make_segment() -> Segment:
    return Segment(
        id="seg-1",
        source_id="clip-1",
        start_ms=1_000,
        end_ms=5_000,
        kind=SegmentKind.DETAIL,
        activity_score=0.8,
        detail_score=0.9,
        audio_score=0.6,
        roi_confidence=0.95,
        recommended_speed=2,
        keep_default=True,
        reason_codes=["detail_high"],
    )


def test_segment_rejects_reversed_range() -> None:
    values = make_segment().model_dump()
    values.update(start_ms=5_000, end_ms=1_000)

    with pytest.raises(ValidationError, match="end_ms must be greater"):
        Segment.model_validate(values)


def test_timeline_item_rejects_noncanonical_speed() -> None:
    with pytest.raises(ValidationError):
        TimelineItem(
            id="item-1",
            role="body",
            segment_id="seg-1",
            trim_in_ms=0,
            trim_out_ms=1_000,
            speed=3,
        )


def test_variant_slug_is_stable() -> None:
    assert Variant.TIKTOK_FAST.value == "tiktok-fast"
    assert Path(f"painting_{Variant.SHORTS_ASMR.value}.mp4").name == "painting_shorts-asmr.mp4"


def test_timeline_rejects_duplicate_item_ids() -> None:
    item = TimelineItem(
        id="same",
        role="body",
        segment_id="seg-1",
        trim_in_ms=0,
        trim_out_ms=1_000,
        speed=1,
    )

    with pytest.raises(ValidationError, match="item ids must be unique"):
        Timeline(
            variant=Variant.TIKTOK_FAST,
            revision=0,
            audio_mode="asmr",
            items=[item, item],
        )
