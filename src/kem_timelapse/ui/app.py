from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from kem_timelapse.ui.controller import DesktopController
from kem_timelapse.ui.main_window import MainWindow


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    controller = DesktopController(parent=window)
    controller.attach(window)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
