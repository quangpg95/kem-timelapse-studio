from dataclasses import dataclass
from typing import Literal

from kem_timelapse.domain.models import SegmentKind, Speed, Variant


@dataclass(frozen=True)
class ComposerPreset:
    variant: Variant
    min_ms: int
    target_ms: int
    max_ms: int
    hook_ms: int
    reveal_ms: int
    audio_mode: Literal["asmr_music", "asmr", "music", "silent"]
    speed_by_kind: dict[SegmentKind, Speed]
    score_weights: dict[SegmentKind, float]


TIKTOK = ComposerPreset(
    Variant.TIKTOK_FAST,
    25_000,
    30_000,
    35_000,
    1_250,
    2_500,
    "asmr_music",
    {
        SegmentKind.BROAD_FILL: 12,
        SegmentKind.PROGRESS: 12,
        SegmentKind.DETAIL: 4,
        SegmentKind.ASMR_PEAK: 2,
        SegmentKind.REVEAL_CANDIDATE: 1,
    },
    {
        SegmentKind.BROAD_FILL: 1.0,
        SegmentKind.PROGRESS: 1.2,
        SegmentKind.DETAIL: 1.1,
        SegmentKind.ASMR_PEAK: 0.8,
        SegmentKind.REVEAL_CANDIDATE: 2.0,
    },
)
REELS = ComposerPreset(
    Variant.REELS_AESTHETIC,
    35_000,
    42_000,
    50_000,
    1_500,
    4_000,
    "asmr_music",
    {
        SegmentKind.BROAD_FILL: 12,
        SegmentKind.PROGRESS: 4,
        SegmentKind.DETAIL: 2,
        SegmentKind.ASMR_PEAK: 2,
        SegmentKind.REVEAL_CANDIDATE: 1,
    },
    {
        SegmentKind.BROAD_FILL: 0.8,
        SegmentKind.PROGRESS: 1.1,
        SegmentKind.DETAIL: 1.4,
        SegmentKind.ASMR_PEAK: 1.1,
        SegmentKind.REVEAL_CANDIDATE: 2.0,
    },
)
SHORTS = ComposerPreset(
    Variant.SHORTS_ASMR,
    55_000,
    70_000,
    90_000,
    1_500,
    5_000,
    "asmr",
    {
        SegmentKind.BROAD_FILL: 4,
        SegmentKind.PROGRESS: 4,
        SegmentKind.DETAIL: 2,
        SegmentKind.ASMR_PEAK: 1,
        SegmentKind.REVEAL_CANDIDATE: 1,
    },
    {
        SegmentKind.BROAD_FILL: 0.4,
        SegmentKind.PROGRESS: 0.8,
        SegmentKind.DETAIL: 1.6,
        SegmentKind.ASMR_PEAK: 2.0,
        SegmentKind.REVEAL_CANDIDATE: 1.8,
    },
)
