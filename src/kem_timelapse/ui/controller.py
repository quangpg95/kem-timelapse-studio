from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer

from kem_timelapse.domain.errors import PipelineError
from kem_timelapse.domain.models import SourceClip, Variant
from kem_timelapse.editing.session import EditingSession
from kem_timelapse.jobs.cancellation import CancellationToken
from kem_timelapse.storage.project_repository import ProjectRepository
from kem_timelapse.ui.worker import JobWorker

ERROR_COPY = {
    "SourceUnavailable": "Không đọc được video nguồn. Hãy kết nối lại ổ hoặc chọn lại file.",
    "InsufficientDisk": "Không đủ dung lượng cho cache và ba video đầu ra.",
    "RenderBackendUnavailable": "FFmpeg hoặc VideoToolbox chưa sẵn sàng.",
    "OutputNotWritable": "Không thể ghi vào thư mục đầu ra đã chọn.",
    "TimelineInvalid": "Timeline cần được sửa trước khi render.",
    "OutputValidationFailed": "Video render chưa đạt chuẩn đầu ra.",
}


def user_message(error: PipelineError) -> str:
    return ERROR_COPY[error.code.value]


class DesktopController(QObject):
    """Application-service adapter. Widgets only communicate through its signals and methods."""

    def __init__(
        self,
        repository: ProjectRepository | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._worker: JobWorker | None = None
        self._thread: QThread | None = None
        self._window: Any | None = None
        self._editing_sessions: dict[Variant, EditingSession] = {}
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(300)
        self._persist_timer.timeout.connect(self.persist_timelines)

    def attach(self, window: Any) -> None:
        self._window = window
        window.cancel_button.clicked.connect(self.request_cancel)
        window.closing.connect(self.request_cancel)
        window.preview_page.editAccepted.connect(self.schedule_timeline_persistence)
        window.preview_page.cancelRequested.connect(self.request_cancel)

    def persist_sources(self, sources: Sequence[SourceClip]) -> None:
        if self._repository is not None:
            self._repository.save_sources(sources)

    def set_editing_sessions(self, sessions: dict[Variant, EditingSession]) -> None:
        self._editing_sessions = sessions
        if self._window is not None:
            self._window.preview_page.set_sessions(sessions)

    def schedule_timeline_persistence(self) -> None:
        if self._repository is not None:
            self._persist_timer.start()

    def persist_timelines(self) -> None:
        if self._repository is None:
            return
        for session in self._editing_sessions.values():
            self._repository.save_timeline(session.snapshot())

    def start_operation(self, operation: Callable[[CancellationToken], object]) -> None:
        self.request_cancel()
        token = CancellationToken()
        worker = JobWorker(operation, token)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.handle_progress)
        worker.completed.connect(self._completed)
        worker.failed.connect(self._failed)
        worker.cancelled.connect(self._cancelled)
        for terminal in (worker.completed, worker.failed, worker.cancelled):
            terminal.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_thread)
        self._worker = worker
        self._thread = thread
        thread.start()

    def request_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def handle_progress(self, event: object) -> None:
        if self._window is None:
            return
        progress = event.get("progress", 0.0) if isinstance(event, dict) else 0.0
        self._window.analysis_page.set_progress(float(progress))

    def _completed(self, _: object) -> None:
        if self._window is not None:
            self._window.status_label.setText("Phân tích hoàn tất")

    def _cancelled(self) -> None:
        if self._window is not None:
            self._window.status_label.setText("Đã huỷ")

    def _failed(self, error: object) -> None:
        if self._window is None:
            return
        if isinstance(error, PipelineError):
            self._window.status_label.setText(user_message(error))
        else:
            self._window.status_label.setText("Đã xảy ra lỗi không mong muốn.")

    def _clear_thread(self) -> None:
        self._worker = None
        self._thread = None
