from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class AnalysisPage(QWidget):
    """Progress-only page while the core pipeline prepares review timelines."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("analysisPage")
        layout = QVBoxLayout(self)
        self.status_label = QLabel("Đang chờ phân tích…", self)
        self.status_label.setObjectName("analysisStatusLabel")
        layout.addWidget(self.status_label)
        layout.addStretch()

    def set_progress(self, progress: float) -> None:
        self.status_label.setText(f"Đang phân tích… {round(progress * 100)}%")
