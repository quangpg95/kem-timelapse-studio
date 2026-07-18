from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from kem_timelapse.domain.models import Point, Roi


class RoiOverlay(QWidget):
    """Stores an editable normalized canvas quadrilateral above the proxy viewport."""

    roiConfirmed = Signal(Roi)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("roiOverlay")
        self._points: list[tuple[float, float]] = []

    @property
    def has_valid_roi(self) -> bool:
        return len(self._points) == 4 and _is_simple_quad(self._points)

    def set_manual_points(self, points: Sequence[tuple[float, float]]) -> bool:
        if len(points) != 4:
            return False
        clamped = [(min(1.0, max(0.0, x)), min(1.0, max(0.0, y))) for x, y in points]
        if not _is_simple_quad(clamped):
            return False
        self._points = clamped
        self.update()
        return True

    def confirm(self) -> Roi | None:
        if not self.has_valid_roi:
            return None
        roi = Roi(
            points=tuple(Point(x=x, y=y) for x, y in self._points),  # type: ignore[arg-type]
            confidence=1.0,
            manual=True,
        )
        self.roiConfirmed.emit(roi)
        return roi


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _crosses(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> bool:
    first = _orientation(a, b, c) * _orientation(a, b, d) < 0
    second = _orientation(c, d, a) * _orientation(c, d, b) < 0
    return first and second


def _is_simple_quad(points: Sequence[tuple[float, float]]) -> bool:
    return len(points) == 4 and not (
        _crosses(points[0], points[1], points[2], points[3])
        or _crosses(points[1], points[2], points[3], points[0])
    )
