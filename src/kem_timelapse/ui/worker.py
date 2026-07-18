from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from kem_timelapse.jobs.cancellation import CancellationToken


class JobWorker(QObject):
    """Run one cooperative core operation in a dedicated Qt thread."""

    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        operation: Callable[[CancellationToken], object],
        token: CancellationToken,
    ) -> None:
        super().__init__()
        self._operation = operation
        self._token = token

    @Slot()
    def run(self) -> None:
        try:
            result = self._operation(self._token)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(error)
        else:
            if self._token.is_set():
                self.cancelled.emit()
            else:
                self.completed.emit(result)

    @Slot()
    def cancel(self) -> None:
        self._token.cancel()
