from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from kem_timelapse.domain.models import Roi


@dataclass(frozen=True)
class VisualMetrics:
    motion: float
    canvas_change: float
    changed_area: float
    detail: float


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _crop(frame: NDArray[np.uint8], roi: Roi | None) -> NDArray[np.uint8]:
    if roi is None:
        return frame
    height, width = frame.shape[:2]
    xs = [point.x for point in roi.points]
    ys = [point.y for point in roi.points]
    left, right = int(min(xs) * width), int(max(xs) * width)
    top, bottom = int(min(ys) * height), int(max(ys) * height)
    if right <= left or bottom <= top:
        return frame
    return frame[top:bottom, left:right]


def visual_metrics(
    previous: NDArray[np.uint8],
    current: NDArray[np.uint8],
    roi: Roi | None,
) -> VisualMetrics:
    previous_roi = _crop(previous, roi)
    current_roi = _crop(current, roi)
    target_width = 320
    target_height = max(1, round(current_roi.shape[0] * target_width / current_roi.shape[1]))
    size = (target_width, target_height)
    previous_gray = cv2.cvtColor(cv2.resize(previous_roi, size), cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(cv2.resize(current_roi, size), cv2.COLOR_BGR2GRAY)
    difference = cv2.absdiff(previous_gray, current_gray)
    changed = difference > 20
    changed_area = float(changed.mean())
    canvas_change = float(difference.mean()) / 255.0
    flow = cv2.calcOpticalFlowFarneback(
        previous_gray,
        current_gray,
        None,
        0.5,
        3,
        15,
        3,
        5,
        1.2,
        0,
    )
    motion = float(np.linalg.norm(flow, axis=2).mean()) / 8.0
    previous_edges = cv2.Canny(previous_gray, 50, 150) > 0
    current_edges = cv2.Canny(current_gray, 50, 150) > 0
    edge_change = float(np.logical_xor(previous_edges, current_edges).mean())
    return VisualMetrics(
        motion=_clamp(motion),
        canvas_change=_clamp(canvas_change),
        changed_area=_clamp(changed_area),
        detail=_clamp(edge_change * (1.0 - changed_area)),
    )


def brush_band_score(samples: NDArray[np.float32], sample_rate: int) -> float:
    if samples.size == 0 or not np.any(samples):
        return 0.0
    windowed = samples * np.hanning(samples.size)
    power = np.abs(np.fft.rfft(windowed)) ** 2
    frequencies = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    brush_power = float(power[(frequencies >= 3_000) & (frequencies <= 8_000)].sum())
    total_power = float(power[(frequencies >= 80) & (frequencies <= sample_rate / 2)].sum())
    return _clamp(brush_power / total_power) if total_power else 0.0
