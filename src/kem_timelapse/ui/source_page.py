from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_EXTENSIONS = frozenset({".mov", ".mp4"})


class SourcePage(QWidget):
    """Collect and validate immutable source recordings without media work on the GUI thread."""

    sourcesChanged = Signal(object)
    validationChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sourcePage")
        self.setAcceptDrops(True)
        self._paths: list[Path] = []
        self._valid: dict[Path, bool] = {}

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.add_button = QPushButton("Thêm video", self)
        self.add_button.setObjectName("addSourcesButton")
        self.output_button = QPushButton("Thư mục đầu ra", self)
        self.output_button.setObjectName("chooseOutputButton")
        self.music_button = QPushButton("Nhạc nền (tuỳ chọn)", self)
        self.music_button.setObjectName("chooseMusicButton")
        controls.addWidget(self.add_button)
        controls.addWidget(self.output_button)
        controls.addWidget(self.music_button)
        layout.addLayout(controls)

        self.source_list = QListWidget(self)
        self.source_list.setObjectName("sourceList")
        self.source_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        layout.addWidget(self.source_list)

        self.rights_checkbox = QCheckBox("Tôi có quyền sử dụng nhạc đã chọn", self)
        self.rights_checkbox.setObjectName("musicRightsCheckbox")
        layout.addWidget(self.rights_checkbox)
        self.hint_label = QLabel("Kéo video .MOV hoặc .MP4 vào đây.", self)
        layout.addWidget(self.hint_label)

        self.add_button.clicked.connect(self._choose_files)
        self.source_list.model().rowsMoved.connect(self._emit_changed)

    def add_paths(self, paths: Iterable[Path]) -> None:
        additions = self._expand_paths(paths)
        existing = {path.resolve() for path in self._paths}
        for path in additions:
            resolved = path.expanduser().resolve()
            if resolved in existing:
                continue
            existing.add(resolved)
            self._paths.append(resolved)
            self._valid[resolved] = False
            item = QListWidgetItem(f"{resolved.name} — Đang đọc…")
            item.setData(Qt.ItemDataRole.UserRole, resolved)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.source_list.addItem(item)
        self._emit_changed()

    def set_probe_result(self, path: Path, *, valid: bool, summary: str) -> None:
        resolved = path.expanduser().resolve()
        if resolved not in self._paths:
            return
        self._valid[resolved] = valid
        for index in range(self.source_list.count()):
            item = self.source_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == resolved:
                suffix = summary if valid else "Không đọc được"
                item.setText(f"{resolved.name} — {suffix}")
                break
        self._emit_changed()

    def source_count(self) -> int:
        return len(self._paths)

    def selected_paths(self) -> list[Path]:
        selected: list[Path] = []
        for index in range(self.source_list.count()):
            item = self.source_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        self.add_paths(Path(url.toLocalFile()) for url in urls)
        event.acceptProposedAction()

    def _choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn video nguồn",
            filter="Video (*.mov *.MOV *.mp4 *.MP4)",
        )
        self.add_paths(Path(name) for name in names)

    @staticmethod
    def _expand_paths(paths: Iterable[Path]) -> list[Path]:
        expanded: list[Path] = []
        for path in paths:
            candidate = path.expanduser()
            if candidate.is_dir():
                expanded.extend(
                    child
                    for child in sorted(candidate.iterdir())
                    if child.is_file() and child.suffix.lower() in _EXTENSIONS
                )
            elif candidate.is_file() and candidate.suffix.lower() in _EXTENSIONS:
                expanded.append(candidate)
        return expanded

    def _emit_changed(self, *_: object) -> None:
        selected = self.selected_paths()
        self.sourcesChanged.emit(selected)
        enabled = bool(selected) and all(self._valid.get(path, False) for path in selected)
        self.validationChanged.emit(enabled)
