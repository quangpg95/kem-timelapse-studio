from __future__ import annotations

from collections.abc import Sequence

from kem_timelapse.analysis.roi import TrackedRoi
from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import CropOverride, Roi
from kem_timelapse.framing.models import CropKeyframe, FramingPlan

_SMOOTHING_ALPHA = 0.20
_MAX_MOVEMENT_PER_500_MS = 0.05
_LOW_CONFIDENCE = 0.60


def _largest_even(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def _vertical_crop_dimensions(source_width: int, source_height: int) -> tuple[int, int]:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("source dimensions must be positive")
    if source_width >= source_height:
        return _largest_even((source_height * 9) // 16), _largest_even(source_height)
    return _largest_even(source_width), _largest_even(min(source_height, (source_width * 16) // 9))


def _roi_center(roi: Roi) -> tuple[float, float]:
    return (
        sum(point.x for point in roi.points) / len(roi.points),
        sum(point.y for point in roi.points) / len(roi.points),
    )


def _clamp_center(
    center_x: float,
    center_y: float,
    *,
    crop_width: int,
    crop_height: int,
    source_width: int,
    source_height: int,
    scale: float,
) -> tuple[float, float]:
    half_width = crop_width / (source_width * scale) / 2
    half_height = crop_height / (source_height * scale) / 2
    return (
        min(max(center_x, half_width), 1.0 - half_width),
        min(max(center_y, half_height), 1.0 - half_height),
    )


def _velocity_limited(
    previous: tuple[float, float], target: tuple[float, float], elapsed_ms: int
) -> tuple[float, float]:
    maximum_delta = _MAX_MOVEMENT_PER_500_MS * max(1.0, elapsed_ms / 500)
    return tuple(
        previous_value + min(max(target_value - previous_value, -maximum_delta), maximum_delta)
        for previous_value, target_value in zip(previous, target, strict=True)
    )  # type: ignore[return-value]


def plan_vertical_crop(
    samples: Sequence[TrackedRoi],
    source_width: int,
    source_height: int,
    override: CropOverride | None = None,
) -> FramingPlan:
    """Turn tracked canvas observations into bounded, smooth vertical crop keyframes."""
    crop_width, crop_height = _vertical_crop_dimensions(source_width, source_height)
    keyframes: list[CropKeyframe] = []
    warning_codes: list[WarningCode] = []
    requires_manual_roi = False
    previous_center: tuple[float, float] | None = None
    previous_timestamp: int | None = None

    for sample in samples:
        if override is not None:
            center = (override.center_x, override.center_y)
            scale = override.scale
        elif sample.fallback == "center":
            center = (0.5, 0.5)
            scale = 1.0
        elif sample.roi is not None:
            center = _roi_center(sample.roi)
            scale = 1.0
            if sample.roi.confidence < _LOW_CONFIDENCE and not sample.roi.manual:
                requires_manual_roi = True
                if WarningCode.LOW_ROI_CONFIDENCE not in warning_codes:
                    warning_codes.append(WarningCode.LOW_ROI_CONFIDENCE)
        else:
            center = (0.5, 0.5)
            scale = 1.0

        center = _clamp_center(
            *center,
            crop_width=crop_width,
            crop_height=crop_height,
            source_width=source_width,
            source_height=source_height,
            scale=scale,
        )
        if (
            previous_center is not None
            and previous_timestamp is not None
            and sample.fallback != "center"
        ):
            elapsed_ms = max(0, sample.timestamp_ms - previous_timestamp)
            smoothed = (
                previous_center[0] + _SMOOTHING_ALPHA * (center[0] - previous_center[0]),
                previous_center[1] + _SMOOTHING_ALPHA * (center[1] - previous_center[1]),
            )
            center = _velocity_limited(previous_center, smoothed, elapsed_ms)

        keyframes.append(
            CropKeyframe(
                timestamp_ms=sample.timestamp_ms,
                center_x=center[0],
                center_y=center[1],
                scale=scale,
            )
        )
        previous_center = center
        previous_timestamp = sample.timestamp_ms

    return FramingPlan(
        crop_width=crop_width,
        crop_height=crop_height,
        keyframes=keyframes,
        requires_manual_roi=requires_manual_roi,
        warning_codes=warning_codes,
    )
