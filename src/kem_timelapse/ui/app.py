from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from kem_timelapse.ui.controller import DesktopController
from kem_timelapse.ui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    controller = DesktopController(parent=window)
    controller.attach(window)
    if "--smoke-test" in arguments:
        pages = [window.stack.widget(index) for index in range(window.stack.count())]
        if len(pages) != 3 or any(page is None for page in pages):
            return 1
        print("SMOKE_OK")
        window.close()
        return 0
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
