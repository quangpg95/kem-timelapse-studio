from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    SOURCE_UNAVAILABLE = "SourceUnavailable"
    INSUFFICIENT_DISK = "InsufficientDisk"
    RENDER_BACKEND_UNAVAILABLE = "RenderBackendUnavailable"
    OUTPUT_NOT_WRITABLE = "OutputNotWritable"
    TIMELINE_INVALID = "TimelineInvalid"
    OUTPUT_VALIDATION_FAILED = "OutputValidationFailed"


class WarningCode(str, Enum):
    LOW_ROI_CONFIDENCE = "LowRoiConfidence"
    AUDIO_DENOISE_DEGRADED = "AudioDenoiseDegraded"
    NO_SOURCE_AUDIO = "NoSourceAudio"
    TRACKING_LOST = "TrackingLost"
    WATERMARK_PLACEMENT_FALLBACK = "WatermarkPlacementFallback"


class PipelineError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str, *, context: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.context = context
