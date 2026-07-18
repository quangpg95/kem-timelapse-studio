from __future__ import annotations

import threading


class CancellationToken:
    """Thread-safe cooperative cancellation shared by orchestration and child processes."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self.is_set():
            raise InterruptedError("job cancelled")
