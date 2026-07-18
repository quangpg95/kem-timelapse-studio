from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

from kem_timelapse.domain.models import Segment, SegmentKind, Speed, Timeline
from kem_timelapse.editing.commands import EditCommand, SetKeep, SetSpeed

ModelIndex = QModelIndex | QPersistentModelIndex
_ROOT_INDEX = QModelIndex()


class TimelineTableModel(QAbstractTableModel):
    """A presentation-only model which sends edits back to its owning session."""

    KEEP_COLUMN = 0
    LABEL_COLUMN = 1
    SOURCE_TIME_COLUMN = 2
    SPEED_COLUMN = 3
    REASON_COLUMN = 4
    _HEADERS = ("Giữ", "Nhãn", "Thời gian nguồn", "Tốc độ", "Lý do")

    def __init__(
        self,
        timeline: Timeline,
        *,
        segment_lookup: Mapping[str, Segment],
        on_edit: Callable[[EditCommand], object],
    ) -> None:
        super().__init__()
        self._timeline = timeline
        self._segments = segment_lookup
        self._on_edit = on_edit

    def replace_timeline(self, timeline: Timeline) -> None:
        self.beginResetModel()
        self._timeline = timeline
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = _ROOT_INDEX) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._timeline.items)

    def columnCount(self, parent: ModelIndex = _ROOT_INDEX) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._HEADERS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation is Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._HEADERS)
        ):
            return self._HEADERS[section]
        return None

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == self.KEEP_COLUMN:
            return flags | Qt.ItemFlag.ItemIsUserCheckable
        if index.column() == self.SPEED_COLUMN:
            return flags | Qt.ItemFlag.ItemIsEditable
        return flags

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        item = self._timeline.items[index.row()]
        segment = self._segments.get(item.segment_id)
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == self.KEEP_COLUMN:
            return Qt.CheckState.Checked if item.keep else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.ToolTipRole:
            return _reason_copy(segment.reason_codes if segment is not None else [])
        if role == Qt.ItemDataRole.BackgroundRole and segment is not None:
            return _segment_color(segment.kind)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if index.column() == self.KEEP_COLUMN:
            return ""
        if index.column() == self.LABEL_COLUMN:
            return _label(segment.kind if segment is not None else None, item.role)
        if index.column() == self.SOURCE_TIME_COLUMN:
            return f"{item.trim_in_ms / 1000:.1f}–{item.trim_out_ms / 1000:.1f}s"
        if index.column() == self.SPEED_COLUMN:
            return f"{item.speed}×"
        if index.column() == self.REASON_COLUMN:
            return _reason_copy(segment.reason_codes if segment is not None else [])
        return None

    def setData(  # noqa: N802
        self, index: ModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if not index.isValid():
            return False
        item = self._timeline.items[index.row()]
        if index.column() == self.KEEP_COLUMN and role == Qt.ItemDataRole.CheckStateRole:
            self._on_edit(SetKeep(item_id=item.id, keep=value == Qt.CheckState.Checked))
            return True
        if index.column() == self.SPEED_COLUMN and role == Qt.ItemDataRole.EditRole:
            try:
                speed = int(value)
            except (TypeError, ValueError):
                return False
            if speed not in (1, 2, 4, 12):
                return False
            self._on_edit(SetSpeed(item_id=item.id, speed=cast("Speed", speed)))
            return True
        return False


def _label(kind: SegmentKind | None, role: str) -> str:
    if kind is None:
        return role.replace("_", " ").title()
    return kind.value.replace("_", " ").title()


def _segment_color(kind: SegmentKind) -> str:
    colors = {
        SegmentKind.INACTIVE: "#9ca3af",
        SegmentKind.BROAD_FILL: "#60a5fa",
        SegmentKind.PROGRESS: "#6366f1",
        SegmentKind.DETAIL: "#a855f7",
        SegmentKind.ASMR_PEAK: "#14b8a6",
        SegmentKind.HOOK_CANDIDATE: "#22c55e",
        SegmentKind.REVEAL_CANDIDATE: "#22c55e",
    }
    return colors[kind]


def _reason_copy(reasons: list[str]) -> str:
    phrases = {
        "activity_below_exit": "Ít hoạt động",
        "detail_high": "Nét chi tiết",
        "audio_high": "Âm thanh cọ rõ",
    }
    return ", ".join(phrases.get(reason, reason.replace("_", " ")) for reason in reasons)
