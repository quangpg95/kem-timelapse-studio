from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from kem_timelapse.domain.errors import WarningCode


class CropKeyframe(BaseModel):
    timestamp_ms: int = Field(ge=0)
    center_x: float = Field(ge=0.0, le=1.0)
    center_y: float = Field(ge=0.0, le=1.0)
    scale: float = Field(gt=0.0, le=4.0)


class FramingPlan(BaseModel):
    crop_width: int
    crop_height: int
    keyframes: list[CropKeyframe]
    requires_manual_roi: bool
    warning_codes: list[WarningCode]


class WatermarkPlacement(BaseModel):
    corner: Literal["top-left", "bottom-left", "top-right", "bottom-right"]
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    text: str
    opacity: float = Field(ge=0.0, le=1.0)
    warning: WarningCode | None = None
