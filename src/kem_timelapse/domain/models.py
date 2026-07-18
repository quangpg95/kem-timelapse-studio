from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Speed = Literal[1, 2, 4, 12]


class Variant(str, Enum):
    TIKTOK_FAST = "tiktok-fast"
    REELS_AESTHETIC = "reels-aesthetic"
    SHORTS_ASMR = "shorts-asmr"


class SegmentKind(str, Enum):
    INACTIVE = "inactive"
    BROAD_FILL = "broad_fill"
    PROGRESS = "progress"
    DETAIL = "detail"
    ASMR_PEAK = "asmr_peak"
    HOOK_CANDIDATE = "hook_candidate"
    REVEAL_CANDIDATE = "reveal_candidate"


class JobStatus(str, Enum):
    NEW = "New"
    INGESTED = "Ingested"
    ANALYZING = "Analyzing"
    REVIEW_READY = "ReviewReady"
    RENDERING = "Rendering"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class Point(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class Roi(BaseModel):
    points: tuple[Point, Point, Point, Point]
    confidence: float = Field(ge=0.0, le=1.0)
    manual: bool = False


class MediaInfo(BaseModel):
    duration_ms: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps_num: int = Field(gt=0)
    fps_den: int = Field(gt=0)
    codec: str
    rotation_deg: Literal[0, 90, 180, 270] = 0
    has_audio: bool
    creation_time: str | None = None


class SourceClip(BaseModel):
    id: str
    path: Path
    size_bytes: int = Field(gt=0)
    mtime_ns: int = Field(gt=0)
    fingerprint: str
    media: MediaInfo
    order: int = Field(ge=0)
    selected: bool = True


class FeatureWindow(BaseModel):
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    motion_score: float = Field(ge=0.0, le=1.0)
    canvas_change_score: float = Field(ge=0.0, le=1.0)
    changed_area_score: float = Field(ge=0.0, le=1.0)
    detail_score: float = Field(ge=0.0, le=1.0)
    audio_score: float = Field(ge=0.0, le=1.0)
    roi: Roi | None = None

    @model_validator(mode="after")
    def validate_range(self) -> FeatureWindow:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class Segment(BaseModel):
    id: str
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    kind: SegmentKind
    activity_score: float = Field(ge=0.0, le=1.0)
    detail_score: float = Field(ge=0.0, le=1.0)
    audio_score: float = Field(ge=0.0, le=1.0)
    roi_confidence: float = Field(ge=0.0, le=1.0)
    recommended_speed: Speed
    keep_default: bool
    reason_codes: list[str]

    @model_validator(mode="after")
    def validate_range(self) -> Segment:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class CropOverride(BaseModel):
    center_x: float = Field(ge=0.0, le=1.0)
    center_y: float = Field(ge=0.0, le=1.0)
    scale: float = Field(gt=0.0, le=4.0)


class TimelineItem(BaseModel):
    id: str
    role: Literal["hook", "body", "reveal"]
    segment_id: str
    trim_in_ms: int = Field(ge=0)
    trim_out_ms: int = Field(gt=0)
    speed: Speed
    keep: bool = True
    crop_override: CropOverride | None = None

    @model_validator(mode="after")
    def validate_range(self) -> TimelineItem:
        if self.trim_out_ms <= self.trim_in_ms:
            raise ValueError("trim_out_ms must be greater than trim_in_ms")
        return self


class Timeline(BaseModel):
    schema_version: int = 1
    variant: Variant
    revision: int = Field(ge=0)
    audio_mode: Literal["asmr_music", "asmr", "music", "silent"]
    watermark_text: str = "@kem12032024"
    watermark_opacity: float = Field(default=0.30, ge=0.0, le=1.0)
    items: list[TimelineItem]

    @model_validator(mode="after")
    def validate_unique_item_ids(self) -> Timeline:
        item_ids = [item.id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("timeline item ids must be unique")
        return self


class ProjectState(BaseModel):
    schema_version: int = 1
    project_id: str
    name: str
    status: JobStatus = JobStatus.NEW
    resume_from: JobStatus | None = None
    completed_analysis_clip_ids: list[str] = Field(default_factory=list)
    completed_variants: list[Variant] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
