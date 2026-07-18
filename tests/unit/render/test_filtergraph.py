import pytest

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import Segment, SegmentKind, Timeline, TimelineItem, Variant
from kem_timelapse.framing.models import WatermarkPlacement
from kem_timelapse.render.filtergraph import build_video_filtergraph


def segment(segment_id: str = "s1", source_id: str = "clip-1") -> Segment:
    return Segment(
        id=segment_id,
        source_id=source_id,
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


def timeline(items: list[TimelineItem] | None = None) -> Timeline:
    return Timeline(
        variant=Variant.SHORTS_ASMR,
        revision=0,
        audio_mode="asmr",
        items=items
        if items is not None
        else [
            TimelineItem(
                id="shorts-body-s1-0",
                role="body",
                segment_id="s1",
                trim_in_ms=1_000,
                trim_out_ms=5_000,
                speed=2,
            )
        ],
    )


def test_filtergraph_trims_speeds_crops_concats_and_watermarks() -> None:
    graph = build_video_filtergraph(
        timeline(),
        {"s1": segment()},
        input_indexes={"clip-1": 0},
        crop_expressions={"s1": ("1214", "2160", "1313", "0")},
    )

    assert "trim=start=1:end=5" in graph
    assert "setpts=(PTS-STARTPTS)/2" in graph
    assert "crop=1214:2160:1313:0" in graph
    assert "scale=1080:1920" in graph
    assert "concat=n=1:v=1:a=0[joined]" in graph
    assert "drawtext=text='@kem12032024':fontcolor=white@0.3" in graph
    assert graph.endswith("[vout]")


def test_filtergraph_escapes_supported_drawtext_characters() -> None:
    placement = WatermarkPlacement(
        corner="top-left",
        x=0.03,
        y=0.11,
        text=r"KEM: 50% [A] \\ '",
        opacity=0.25,
    )

    graph = build_video_filtergraph(
        timeline(),
        {"s1": segment()},
        input_indexes={"clip-1": 0},
        crop_expressions={"s1": ("1214", "2160", "1313", "0")},
        watermark=placement,
    )

    assert r"KEM\: 50\% \[A\]" in graph
    assert "fontcolor=white@0.25" in graph


@pytest.mark.parametrize(
    ("items", "segments", "indexes", "crops"),
    [
        ([], {"s1": segment()}, {"clip-1": 0}, {"s1": ("1", "1", "0", "0")}),
        (None, {}, {"clip-1": 0}, {"s1": ("1", "1", "0", "0")}),
        (None, {"s1": segment()}, {"clip-1": -1}, {"s1": ("1", "1", "0", "0")}),
        (None, {"s1": segment()}, {"clip-1": 0}, {}),
    ],
)
def test_filtergraph_rejects_invalid_timeline_inputs(
    items: list[TimelineItem] | None,
    segments: dict[str, Segment],
    indexes: dict[str, int],
    crops: dict[str, tuple[str, str, str, str]],
) -> None:
    candidate = timeline(items)
    if items is None and not segments:
        candidate = timeline()

    with pytest.raises(PipelineError) as caught:
        build_video_filtergraph(candidate, segments, indexes, crops)

    assert caught.value.code is ErrorCode.TIMELINE_INVALID


def test_filtergraph_rejects_control_characters_in_watermark() -> None:
    candidate = timeline().model_copy(update={"watermark_text": "unsafe\ntext"})

    with pytest.raises(PipelineError) as caught:
        build_video_filtergraph(
            candidate,
            {"s1": segment()},
            {"clip-1": 0},
            {"s1": ("1214", "2160", "1313", "0")},
        )

    assert caught.value.code is ErrorCode.TIMELINE_INVALID
