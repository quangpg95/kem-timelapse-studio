from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Variant


class RenderPlan(BaseModel):
    variant: Variant
    source_paths: list[Path]
    audio_mix_path: Path
    video_filter_graph: str
    ffmpeg_args: list[str]
    final_path: Path
    temporary_path: Path
    expected_duration_ms: int = Field(gt=0)
    warning_codes: list[WarningCode]


class OutputProbe(BaseModel):
    path: Path
    video_codec: str
    width: int
    height: int
    pixel_format: str
    fps: float
    audio_codec: str
    has_aac: bool
    start_time_ms: int
    duration_ms: int = Field(gt=0)


class ManifestEntry(BaseModel):
    variant: Variant
    filename: str
    sha256: str = Field(min_length=64, max_length=64)
    timeline_revision: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0.0)
    probe: OutputProbe
    warning_codes: list[WarningCode]
    source_fingerprints: dict[str, str]
    analyzer_version: str
    composer_version: str
    audio_preset_version: str
