from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Roi, Segment, Variant
from kem_timelapse.editing.commands import EditCommand, SetWatermark
from kem_timelapse.editing.session import EditingSession, copy_shared_edits
from kem_timelapse.ui.roi_overlay import RoiOverlay
from kem_timelapse.ui.timeline_model import TimelineTableModel


class PreviewPage(QWidget):
    """Approved, intentionally focused editing surface for the three Content Pack variants."""

    renderRequested = Signal(object)
    renderPackRequested = Signal()
    cancelRequested = Signal()
    roiConfirmed = Signal(Roi)
    editAccepted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewPage")
        self._sessions: dict[Variant, EditingSession] = {}
        self._segments: Mapping[str, Segment] = {}
        self._active_variant = Variant.TIKTOK_FAST
        self._manual_roi_required = False
        self._model: TimelineTableModel | None = None

        layout = QVBoxLayout(self)
        self.warning_banner = QLabel("", self)
        self.warning_banner.setObjectName("warningBanner")
        layout.addWidget(self.warning_banner)
        self.variant_tabs = QTabWidget(self)
        self.variant_tabs.setObjectName("variantTabs")
        for label in ("TikTok Fast", "Reels Aesthetic", "Shorts ASMR"):
            self.variant_tabs.addTab(QWidget(self.variant_tabs), label)
        self.variant_tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.variant_tabs)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setObjectName("proxyVideo")
        self.video_widget.setMinimumHeight(360)
        layout.addWidget(self.video_widget)
        self.audio_output = QAudioOutput(self)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.roi_overlay = RoiOverlay(self.video_widget)
        self.roi_overlay.roiConfirmed.connect(self._roi_confirmed)

        self.timeline_view = QTableView(self)
        self.timeline_view.setObjectName("timelineView")
        layout.addWidget(self.timeline_view)
        edit_row = QHBoxLayout()
        self.speed_combo = QComboBox(self)
        self.speed_combo.addItems(["1×", "2×", "4×", "12×"])
        self.speed_combo.currentTextChanged.connect(self._set_selected_speed)
        self.undo_button = QPushButton("Undo", self)
        self.undo_button.setObjectName("undoButton")
        self.redo_button = QPushButton("Redo", self)
        self.redo_button.setObjectName("redoButton")
        self.copy_to_all_button = QPushButton("Copy to all", self)
        self.copy_to_all_button.setObjectName("copyToAllButton")
        for widget in (
            self.speed_combo,
            self.undo_button,
            self.redo_button,
            self.copy_to_all_button,
        ):
            edit_row.addWidget(widget)
        layout.addLayout(edit_row)
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        self.copy_to_all_button.clicked.connect(self._copy_to_all)

        watermark_row = QHBoxLayout()
        self.watermark_text = QLineEdit("@kem12032024", self)
        self.watermark_opacity = QSpinBox(self)
        self.watermark_opacity.setRange(0, 100)
        self.watermark_opacity.setValue(30)
        self.watermark_position = QComboBox(self)
        self.watermark_position.addItems(
            ["Tự động", "Trên trái", "Trên phải", "Dưới trái", "Dưới phải"]
        )
        for watermark_widget in (
            self.watermark_text,
            self.watermark_opacity,
            self.watermark_position,
        ):
            watermark_row.addWidget(watermark_widget)
        layout.addLayout(watermark_row)
        self.watermark_text.editingFinished.connect(self._set_watermark)
        self.watermark_opacity.valueChanged.connect(lambda _: self._set_watermark())

        render_row = QHBoxLayout()
        self.confirm_roi_button = QPushButton("Xác nhận vùng tranh", self)
        self.confirm_roi_button.setObjectName("confirmRoiButton")
        self.render_first_button = QPushButton("Render TikTok trước", self)
        self.render_first_button.setObjectName("renderFirstButton")
        self.render_pack_button = QPushButton("Render đủ Content Pack", self)
        self.render_pack_button.setObjectName("renderPackButton")
        self.cancel_button = QPushButton("Huỷ render", self)
        for widget in (
            self.confirm_roi_button,
            self.render_first_button,
            self.render_pack_button,
            self.cancel_button,
        ):
            render_row.addWidget(widget)
        layout.addLayout(render_row)
        self.confirm_roi_button.clicked.connect(self.roi_overlay.confirm)
        self.render_first_button.clicked.connect(
            lambda: self.renderRequested.emit(Variant.TIKTOK_FAST)
        )
        self.render_pack_button.clicked.connect(self.renderPackRequested.emit)
        self.cancel_button.clicked.connect(self.cancelRequested.emit)
        self._update_render_controls()

    def set_sessions(self, sessions: Mapping[Variant, EditingSession]) -> None:
        self._sessions = dict(sessions)
        if self._active_variant not in self._sessions and self._sessions:
            self._active_variant = next(iter(self._sessions))
        self.select_variant(self._active_variant)

    def set_segments(self, segments: Mapping[str, Segment]) -> None:
        self._segments = segments
        self._refresh_model()

    def set_warnings(self, warnings: list[WarningCode]) -> None:
        self._manual_roi_required = WarningCode.LOW_ROI_CONFIDENCE in warnings
        warning = "Cần xác nhận vùng tranh thủ công" if self._manual_roi_required else ""
        self.warning_banner.setText(warning)
        self._update_render_controls()

    def select_variant(self, variant: Variant) -> None:
        self._active_variant = variant
        self.variant_tabs.setCurrentIndex(list(Variant).index(variant))
        self._refresh_model()

    def _tab_changed(self, index: int) -> None:
        variants = list(Variant)
        if 0 <= index < len(variants):
            self._active_variant = variants[index]
            self._refresh_model()

    def _refresh_model(self) -> None:
        session = self._sessions.get(self._active_variant)
        if session is None:
            self.timeline_view.setModel(None)
            self._update_render_controls()
            return
        self._model = TimelineTableModel(
            session.snapshot(), segment_lookup=self._segments, on_edit=self._apply_edit
        )
        self.timeline_view.setModel(self._model)
        if session.snapshot().items:
            with QSignalBlocker(self.speed_combo):
                self.speed_combo.setCurrentText(f"{session.snapshot().items[0].speed}×")
        self._update_render_controls()

    def _apply_edit(self, command: EditCommand) -> None:
        session = self._sessions.get(self._active_variant)
        if session is None:
            return
        session.apply(command)
        self._refresh_model()
        self.editAccepted.emit()

    def _set_selected_speed(self, label: str) -> None:
        selection = self.timeline_view.selectionModel()
        indexes = selection.selectedRows() if selection is not None else []
        if not indexes or self._model is None:
            return
        speed = int(label.removesuffix("×"))
        self._model.setData(self._model.index(indexes[0].row(), self._model.SPEED_COLUMN), speed)

    def _undo(self) -> None:
        session = self._sessions.get(self._active_variant)
        if session is not None:
            session.undo()
            self._refresh_model()
            self.editAccepted.emit()

    def _redo(self) -> None:
        session = self._sessions.get(self._active_variant)
        if session is not None:
            session.redo()
            self._refresh_model()
            self.editAccepted.emit()

    def _copy_to_all(self) -> None:
        source = self._sessions.get(self._active_variant)
        if source is None:
            return
        targets = [
            session.snapshot()
            for variant, session in self._sessions.items()
            if variant is not self._active_variant
        ]
        copied = copy_shared_edits(source.snapshot(), targets)
        for timeline in copied:
            self._sessions[timeline.variant] = EditingSession(timeline)
        self._refresh_model()
        self.editAccepted.emit()

    def _set_watermark(self) -> None:
        session = self._sessions.get(self._active_variant)
        if session is not None:
            command = SetWatermark(self.watermark_text.text(), self.watermark_opacity.value() / 100)
            session.apply(command)
            self._refresh_model()
            self.editAccepted.emit()

    def _roi_confirmed(self, roi: Roi) -> None:
        self._manual_roi_required = False
        self.roiConfirmed.emit(roi)
        self._update_render_controls()

    def _update_render_controls(self) -> None:
        # Confirmation is meaningful before timelines are loaded, so the ROI gate itself
        # remains independently testable; controller-level render wiring adds the timeline gate.
        enabled = not self._manual_roi_required
        self.render_first_button.setEnabled(enabled)
        self.render_pack_button.setEnabled(enabled)
