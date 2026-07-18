from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Variant


class SourceRange(BaseModel):
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> SourceRange:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class AudioStem(BaseModel):
    source_range: SourceRange
    path: Path
    cache_key: str
    warning: WarningCode | None = None


class DenoiseResult(BaseModel):
    path: Path
    warning: WarningCode | None = None


class AudioMixPlan(BaseModel):
    variant: Variant
    mode: Literal["asmr_music", "asmr", "music", "silent"]
    stem_paths: list[Path]
    music_path: Path | None
    filter_graph: str
    mix_path: Path
    warning_codes: list[WarningCode]
