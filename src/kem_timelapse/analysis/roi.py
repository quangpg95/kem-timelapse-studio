from __future__ import annotations

from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from kem_timelapse.domain.models import Point, Roi


class TrackedRoi(BaseModel):
    timestamp_ms: int
    roi: Roi | None
    fallback: Literal["none", "hold", "center"]
    warning: bool


def _ordered(points: NDArray[np.float32]) -> NDArray[np.float32]:
    result: NDArray[np.float32] = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    result[0] = points[np.argmin(sums)]
    result[2] = points[np.argmax(sums)]
    result[1] = points[np.argmin(differences)]
    result[3] = points[np.argmax(differences)]
    return result


def detect_canvas_roi(frame: NDArray[np.uint8]) -> Roi | None:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[float, NDArray[np.float32]]] = []
    frame_area = float(width * height)
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        area = float(abs(cv2.contourArea(polygon)))
        if area / frame_area < 0.08:
            continue
        rectangle = cv2.minAreaRect(polygon)
        box_area = max(1.0, float(rectangle[1][0] * rectangle[1][1]))
        rectangularity = min(1.0, area / box_area)
        confidence = 0.5 * rectangularity + 0.5 * min(1.0, (area / frame_area) / 0.30)
        candidates.append((confidence, polygon.reshape(4, 2).astype(np.float32)))
    if not candidates:
        return None
    confidence, pixels = max(candidates, key=lambda item: item[0])
    points = _ordered(pixels)
    normalized = cast(
        tuple[Point, Point, Point, Point],
        tuple(Point(x=float(x / width), y=float(y / height)) for x, y in points),
    )
    return Roi(points=normalized, confidence=confidence)


class RoiTracker:
    def __init__(self, *, alpha: float = 0.25, hold_ms: int = 1_000) -> None:
        self._alpha = alpha
        self._hold_ms = hold_ms
        self._last: Roi | None = None
        self._last_seen_ms: int | None = None

    def update(self, timestamp_ms: int, observation: Roi | None) -> TrackedRoi:
        if observation is not None:
            if self._last is not None and not observation.manual:
                points = cast(
                    tuple[Point, Point, Point, Point],
                    tuple(
                        Point(
                            x=self._alpha * current.x + (1 - self._alpha) * previous.x,
                            y=self._alpha * current.y + (1 - self._alpha) * previous.y,
                        )
                        for current, previous in zip(
                            observation.points,
                            self._last.points,
                            strict=True,
                        )
                    ),
                )
                observation = Roi(points=points, confidence=observation.confidence)
            self._last = observation
            self._last_seen_ms = timestamp_ms
            return TrackedRoi(
                timestamp_ms=timestamp_ms,
                roi=observation,
                fallback="none",
                warning=False,
            )
        if self._last is not None and self._last_seen_ms is not None:
            if timestamp_ms - self._last_seen_ms <= self._hold_ms:
                held = self._last.model_copy(update={"confidence": self._last.confidence * 0.8})
                return TrackedRoi(
                    timestamp_ms=timestamp_ms,
                    roi=held,
                    fallback="hold",
                    warning=False,
                )
        return TrackedRoi(timestamp_ms=timestamp_ms, roi=None, fallback="center", warning=True)
