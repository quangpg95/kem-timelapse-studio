from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import cv2
from numpy.typing import NDArray

from kem_timelapse.analysis.features import VisualMetrics, visual_metrics
from kem_timelapse.analysis.roi import RoiTracker, TrackedRoi, detect_canvas_roi
from kem_timelapse.analysis.sampling import sampling_schedule
from kem_timelapse.domain.models import FeatureWindow, Roi
from kem_timelapse.media.proxy import ProxyArtifact

AudioEnvelope = Callable[[int], float]
RoiDetector = Callable[[NDArray], Roi | None]


class CancellationEvent(Protocol):
    def is_set(self) -> bool: ...


class FrameReader(Protocol):
    def read(self, timestamp_ms: int) -> NDArray | None: ...

    def close(self) -> None: ...


FrameReaderFactory = Callable[[Path], FrameReader]


class OpenCvFrameReader:
    def __init__(self, path: Path) -> None:
        self._capture = cv2.VideoCapture(str(path))
        if not self._capture.isOpened():
            self._capture.release()
            raise OSError(f"cannot open proxy: {path}")
        if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
            self._capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)

    def read(self, timestamp_ms: int) -> NDArray | None:
        self._capture.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)
        ok, frame = self._capture.read()
        return frame if ok else None

    def close(self) -> None:
        self._capture.release()


class HeuristicAnalyzer:
    def __init__(
        self,
        *,
        frame_reader_factory: FrameReaderFactory = OpenCvFrameReader,
        roi_detector: RoiDetector = detect_canvas_roi,
        sparse_ms: int = 1_000,
        dense_ms: int = 100,
    ) -> None:
        self._frame_reader_factory = frame_reader_factory
        self._roi_detector = roi_detector
        self._sparse_ms = sparse_ms
        self._dense_ms = dense_ms

    def analyze(
        self,
        proxy: ProxyArtifact,
        audio_envelope: AudioEnvelope,
        cancel_event: CancellationEvent,
    ) -> list[FeatureWindow]:
        reader = self._frame_reader_factory(proxy.path)
        try:
            candidates = self._candidate_timestamps(
                reader,
                proxy.duration_ms,
                audio_envelope,
                cancel_event,
            )
            schedule = sampling_schedule(
                proxy.duration_ms,
                candidates,
                sparse_ms=self._sparse_ms,
                dense_ms=self._dense_ms,
            )
            return self._feature_windows(
                reader,
                proxy.source_id,
                schedule,
                audio_envelope,
                cancel_event,
            )
        finally:
            reader.close()

    def _candidate_timestamps(
        self,
        reader: FrameReader,
        duration_ms: int,
        audio_envelope: AudioEnvelope,
        cancel_event: CancellationEvent,
    ) -> list[int]:
        schedule = sampling_schedule(
            duration_ms,
            [],
            sparse_ms=self._sparse_ms,
            dense_ms=self._dense_ms,
        )
        tracker = RoiTracker()
        candidates: list[int] = []
        previous_frame: NDArray | None = None
        for timestamp_ms in schedule:
            frame = self._read_frame(reader, timestamp_ms, cancel_event)
            tracked = tracker.update(timestamp_ms, self._roi_detector(frame))
            audio_score = _clamp(audio_envelope(timestamp_ms))
            if previous_frame is not None:
                scores = visual_metrics(previous_frame, frame, tracked.roi)
                if _is_candidate(scores, audio_score):
                    candidates.append(timestamp_ms)
            elif audio_score > 0.10:
                candidates.append(timestamp_ms)
            previous_frame = frame
        return candidates

    def _feature_windows(
        self,
        reader: FrameReader,
        source_id: str,
        schedule: list[int],
        audio_envelope: AudioEnvelope,
        cancel_event: CancellationEvent,
    ) -> list[FeatureWindow]:
        if len(schedule) < 2:
            return []
        tracker = RoiTracker()
        frames: list[NDArray] = []
        tracked_rois: list[TrackedRoi] = []
        for timestamp_ms in schedule:
            frame = self._read_frame(reader, timestamp_ms, cancel_event)
            frames.append(frame)
            tracked_rois.append(tracker.update(timestamp_ms, self._roi_detector(frame)))

        windows: list[FeatureWindow] = []
        for index, (start_ms, end_ms) in enumerate(
            zip(schedule, schedule[1:], strict=False)
        ):
            start_roi = tracked_rois[index].roi
            metric_roi = tracked_rois[index + 1].roi or start_roi
            scores = visual_metrics(frames[index], frames[index + 1], metric_roi)
            windows.append(
                FeatureWindow(
                    source_id=source_id,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    motion_score=scores.motion,
                    canvas_change_score=scores.canvas_change,
                    changed_area_score=scores.changed_area,
                    detail_score=scores.detail,
                    audio_score=_clamp(audio_envelope(start_ms)),
                    roi=start_roi,
                )
            )
        return windows

    @staticmethod
    def _read_frame(
        reader: FrameReader,
        timestamp_ms: int,
        cancel_event: CancellationEvent,
    ) -> NDArray:
        if cancel_event.is_set():
            raise InterruptedError("analysis cancelled")
        frame = reader.read(timestamp_ms)
        if frame is None:
            raise OSError(f"cannot decode proxy frame at {timestamp_ms} ms")
        return frame


def _is_candidate(scores: VisualMetrics, audio_score: float) -> bool:
    return max(
        scores.motion,
        scores.canvas_change,
        scores.detail,
        audio_score,
    ) > 0.10


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
