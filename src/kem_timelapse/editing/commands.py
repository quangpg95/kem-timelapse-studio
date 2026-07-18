from __future__ import annotations

from dataclasses import dataclass

from kem_timelapse.domain.models import CropOverride, Speed


@dataclass(frozen=True)
class SetKeep:
    item_id: str
    keep: bool


@dataclass(frozen=True)
class SetSpeed:
    item_id: str
    speed: Speed


@dataclass(frozen=True)
class SetCrop:
    item_id: str
    crop: CropOverride | None


@dataclass(frozen=True)
class SetWatermark:
    text: str
    opacity: float


EditCommand = SetKeep | SetSpeed | SetCrop | SetWatermark
