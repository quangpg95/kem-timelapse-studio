from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, TypeAlias

import numpy as np
from numpy.typing import NDArray

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.framing.models import WatermarkPlacement

_MARGIN = 0.03
_TOP_RESERVED = 0.08
_BOTTOM_RESERVED = 0.18
_RIGHT_RESERVED = 0.15
_TEXT_HEIGHT = 0.035

Rect = tuple[float, float, float, float]
Corner: TypeAlias = Literal["top-left", "bottom-left", "top-right", "bottom-right"]


def _text_width(text: str) -> float:
    return min(0.30, max(0.10, len(text) * 0.012))


def _overlaps(first: Rect, second: Rect) -> bool:
    horizontal = first[0] < second[2] and second[0] < first[2]
    vertical = first[1] < second[3] and second[1] < first[3]
    return horizontal and vertical


def _mean_saliency(saliency: NDArray[np.float32], rect: Rect) -> float:
    height, width = saliency.shape
    left = max(0, min(width, int(np.floor(rect[0] * width))))
    right = max(left + 1, min(width, int(np.ceil(rect[2] * width))))
    top = max(0, min(height, int(np.floor(rect[1] * height))))
    bottom = max(top + 1, min(height, int(np.ceil(rect[3] * height))))
    return float(saliency[top:bottom, left:right].mean())


def _candidates(text: str) -> Iterable[tuple[Corner, float, float, Rect]]:
    width = _text_width(text)
    bottom_y = 1.0 - _BOTTOM_RESERVED - _MARGIN - _TEXT_HEIGHT
    top_y = _TOP_RESERVED + _MARGIN
    left_x = _MARGIN
    right_x = 1.0 - _RIGHT_RESERVED - _MARGIN - width
    positions: tuple[tuple[Corner, float, float], ...] = (
        ("bottom-left", left_x, bottom_y),
        ("top-left", left_x, top_y),
        ("bottom-right", right_x, bottom_y),
        ("top-right", right_x, top_y),
    )
    for corner, x, y in positions:
        yield corner, x, y, (x, y, x + width, y + _TEXT_HEIGHT)


def choose_watermark_placement(
    saliency: NDArray[np.float32],
    canvas_box: Rect,
    text: str,
    opacity: float,
) -> WatermarkPlacement:
    """Choose the least-salient platform-safe watermark location outside the canvas."""
    if saliency.ndim != 2 or saliency.size == 0:
        raise ValueError("saliency must be a non-empty two-dimensional grid")

    available: list[tuple[float, int, Corner, float, float]] = []
    for order, (corner, x, y, text_box) in enumerate(_candidates(text)):
        if not _overlaps(text_box, canvas_box):
            available.append((_mean_saliency(saliency, text_box), order, corner, x, y))

    if not available:
        corner, x, y, _ = next(iter(_candidates(text)))
        return WatermarkPlacement(
            corner=corner,
            x=x,
            y=y,
            text=text,
            opacity=opacity,
            warning=WarningCode.WATERMARK_PLACEMENT_FALLBACK,
        )

    _, _, corner, x, y = min(available)
    return WatermarkPlacement(corner=corner, x=x, y=y, text=text, opacity=opacity)
