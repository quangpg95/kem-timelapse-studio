from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kem_timelapse.ui.analysis_page import AnalysisPage
from kem_timelapse.ui.preview_page import PreviewPage
from kem_timelapse.ui.source_page import SourcePage


class MainWindow(QMainWindow):
    """Stable three-step desktop shell; preview controls arrive in Task 15."""

    closing = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Kem Timelapse Studio")
        central = QWidget(self)
        layout = QVBoxLayout(central)
        step_row = QHBoxLayout()
        self.step_buttons = [
            QPushButton("1. Nguồn quay", central),
            QPushButton("2. Phân tích", central),
            QPushButton("3. Preview & Render", central),
        ]
        for button in self.step_buttons:
            button.setCheckable(False)
            button.setEnabled(False)
            step_row.addWidget(button)
        layout.addLayout(step_row)

        self.stack = QStackedWidget(central)
        self.source_page = SourcePage(self.stack)
        self.analysis_page = AnalysisPage(self.stack)
        self.preview_page = PreviewPage(self.stack)
        self.stack.addWidget(self.source_page)
        self.stack.addWidget(self.analysis_page)
        self.stack.addWidget(self.preview_page)
        layout.addWidget(self.stack)

        action_row = QHBoxLayout()
        self.back_button = QPushButton("Quay lại", central)
        self.back_button.setObjectName("backButton")
        self.analyze_button = QPushButton("Phân tích", central)
        self.analyze_button.setObjectName("analyzeButton")
        self.analyze_button.setEnabled(False)
        self.cancel_button = QPushButton("Huỷ", central)
        self.cancel_button.setObjectName("cancelButton")
        self.continue_button = QPushButton("Tiếp tục / Render", central)
        self.continue_button.setObjectName("continueRenderButton")
        action_row.addWidget(self.back_button)
        action_row.addWidget(self.analyze_button)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.continue_button)
        layout.addLayout(action_row)

        self.status_label = QLabel("Sẵn sàng", central)
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        self.setCentralWidget(central)
        self.source_page.validationChanged.connect(self.analyze_button.setEnabled)
        self.back_button.clicked.connect(lambda: self.stack.setCurrentWidget(self.source_page))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closing.emit()
        event.accept()
