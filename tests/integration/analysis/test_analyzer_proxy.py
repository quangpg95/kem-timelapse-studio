from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np
import pytest

from kem_timelapse.analysis.analyzer import HeuristicAnalyzer
from kem_timelapse.media.proxy import ProxyArtifact


def _generated_proxy(path: Path) -> ProxyArtifact:
    width, height, fps = 1_280, 720, 10
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MP4 writer is unavailable")

    final_canvas = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.rectangle(final_canvas, (240, 140), (1_040, 580), (255, 255, 255), -1)
    try:
        for frame_index in range(40):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            if 10 <= frame_index < 20:
                progress = 0.6 if frame_index < 15 else 1.0
                right = 240 + round(800 * progress)
                bottom = 140 + round(440 * progress)
                cv2.rectangle(frame, (240, 140), (right, bottom), (255, 255, 255), -1)
            elif 20 <= frame_index < 30:
                frame = final_canvas.copy()
                offset = (frame_index - 20) * 45
                cv2.line(
                    frame,
                    (360 + offset, 260),
                    (440 + offset, 340),
                    (0, 0, 0),
                    3,
                )
            elif frame_index >= 30:
                frame = final_canvas.copy()
            writer.write(frame)
    finally:
        writer.release()

    return ProxyArtifact(
        source_id="clip-generated",
        path=path,
        width=width,
        height=height,
        fps=fps,
        duration_ms=4_000,
        cache_key="generated-proxy",
    )


def test_analyzer_extracts_activity_from_generated_proxy(tmp_path: Path) -> None:
    proxy = _generated_proxy(tmp_path / "painting-proxy.mp4")
    analyzer = HeuristicAnalyzer()

    def audio_envelope(timestamp_ms: int) -> float:
        return 0.9 if 2_000 <= timestamp_ms < 3_000 else 0.0

    windows = analyzer.analyze(proxy, audio_envelope, threading.Event())

    assert windows[0].motion_score < 0.05
    assert max(window.changed_area_score for window in windows[10:20]) > 0.20
    assert max(window.detail_score for window in windows[20:30]) > windows[0].detail_score
    assert max(window.audio_score for window in windows[20:30]) == 0.9
