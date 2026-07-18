from pathlib import Path

import cv2
import numpy as np

from kem_timelapse.analysis.roi import RoiTracker, detect_canvas_roi


def canvas_frame() -> np.ndarray:
    frame = np.full((720, 1280, 3), 35, dtype=np.uint8)
    cv2.rectangle(frame, (220, 110), (1060, 650), (245, 245, 245), thickness=-1)
    cv2.rectangle(frame, (220, 110), (1060, 650), (120, 120, 120), thickness=8)
    return frame


def test_detect_canvas_returns_normalized_clockwise_quad() -> None:
    roi = detect_canvas_roi(canvas_frame())

    assert roi is not None
    assert roi.confidence >= 0.70
    assert abs(roi.points[0].x - 220 / 1280) < 0.03
    assert abs(roi.points[0].y - 110 / 720) < 0.03


def test_tracker_holds_then_centers_after_loss() -> None:
    detected = detect_canvas_roi(canvas_frame())
    assert detected is not None
    tracker = RoiTracker(alpha=0.25, hold_ms=1_000)

    assert tracker.update(0, detected).fallback == "none"
    assert tracker.update(500, None).fallback == "hold"
    lost = tracker.update(1_500, None)

    assert lost.fallback == "center"
    assert lost.warning is True


def test_detect_canvas_on_committed_fixture() -> None:
    frame = cv2.imread(str(Path("tests/fixtures/images/canvas-rectangle.png")))
    assert frame is not None

    roi = detect_canvas_roi(frame)

    assert roi is not None
    assert roi.confidence >= 0.70
