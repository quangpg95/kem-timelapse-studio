from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class QualityReport(BaseModel):
    """Auditable duration-overlap measurements for the acceptance quality gate."""

    inactivity_removed: float = Field(ge=0.0, le=1.0)
    important_detail_retained: float = Field(ge=0.0, le=1.0)
    inactivity_removed_ms: int = Field(ge=0)
    inactivity_labeled_ms: int = Field(gt=0)
    important_detail_retained_ms: int = Field(ge=0)
    important_detail_labeled_ms: int = Field(gt=0)
    passes_quality_gate: bool


class BenchmarkSource(BaseModel):
    """Shareable source metadata. Deliberately stores a basename, never a path."""

    filename: str
    codec: str
    duration_ms: int = Field(gt=0)
    size_bytes: int = Field(gt=0)
    unchanged: bool


class BenchmarkEnvironment(BaseModel):
    platform: str
    machine: str
    free_disk_bytes: int = Field(ge=0)
    volume_type: str
    power_source: str
    thermal_state: str


class BenchmarkOutput(BaseModel):
    variant: str
    filename: str
    valid: bool
    probe: dict[str, Any]


class BenchmarkReport(BaseModel):
    schema_version: int = 1
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    app_version: str
    ffmpeg_version: str
    sources: list[BenchmarkSource]
    environment: BenchmarkEnvironment
    stage_seconds: dict[str, float]
    outputs: list[BenchmarkOutput]
    warning_codes: list[str]
    quality: QualityReport
    time_to_first_output_seconds: float = Field(ge=0.0)
    full_pack_seconds: float = Field(ge=0.0)
    passes_output_gate: bool
    passes_time_gate: bool

    @property
    def passes(self) -> bool:
        return (
            self.passes_output_gate
            and self.passes_time_gate
            and self.quality.passes_quality_gate
            and all(source.unchanged for source in self.sources)
        )
