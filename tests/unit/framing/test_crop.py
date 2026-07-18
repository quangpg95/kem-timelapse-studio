from kem_timelapse.analysis.roi import TrackedRoi
from kem_timelapse.domain.models import Point, Roi
from kem_timelapse.framing.crop import plan_vertical_crop


def roi(center_x: float, confidence: float = 0.9, manual: bool = False) -> Roi:
    return Roi(
        points=(
            Point(x=center_x - 0.2, y=0.2),
            Point(x=center_x + 0.2, y=0.2),
            Point(x=center_x + 0.2, y=0.8),
            Point(x=center_x - 0.2, y=0.8),
        ),
        confidence=confidence,
        manual=manual,
    )


def test_crop_smooths_motion_and_requires_manual_low_confidence() -> None:
    samples = [
        TrackedRoi(timestamp_ms=0, roi=roi(0.4), fallback="none", warning=False),
        TrackedRoi(timestamp_ms=500, roi=roi(0.8), fallback="none", warning=False),
        TrackedRoi(
            timestamp_ms=1_000,
            roi=roi(0.8, confidence=0.4),
            fallback="none",
            warning=False,
        ),
    ]

    plan = plan_vertical_crop(samples, source_width=3840, source_height=2160)

    assert plan.keyframes[1].center_x < 0.8
    assert plan.requires_manual_roi is True
    assert plan.crop_width == 1214 and plan.crop_height == 2160


def test_crop_velocity_is_clamped_and_center_fallback_is_stable() -> None:
    samples = [
        TrackedRoi(timestamp_ms=0, roi=roi(0.2), fallback="none", warning=False),
        TrackedRoi(timestamp_ms=500, roi=roi(0.8), fallback="none", warning=False),
        TrackedRoi(timestamp_ms=1_500, roi=None, fallback="center", warning=True),
    ]

    plan = plan_vertical_crop(samples, source_width=3840, source_height=2160)

    assert plan.keyframes[1].center_x - plan.keyframes[0].center_x <= 0.05
    assert plan.keyframes[-1].center_x == 0.5
    assert plan.crop_width % 2 == 0 and plan.crop_height % 2 == 0


def test_manual_roi_clears_low_confidence_block() -> None:
    sample = TrackedRoi(
        timestamp_ms=0,
        roi=roi(0.5, confidence=0.4, manual=True),
        fallback="none",
        warning=False,
    )

    assert plan_vertical_crop([sample], 3840, 2160).requires_manual_roi is False
