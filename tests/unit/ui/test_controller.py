import threading

from PySide6.QtCore import QThread, QTimer

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.jobs.cancellation import CancellationToken
from kem_timelapse.ui.controller import ERROR_COPY, DesktopController, user_message
from kem_timelapse.ui.worker import JobWorker


def start_worker_thread(worker: JobWorker) -> QThread:
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.completed.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.cancelled.connect(thread.quit)
    thread.start()
    return thread


def test_worker_cancel_sets_token_and_emits_cancelled(qtbot) -> None:
    entered = threading.Event()
    token = CancellationToken()

    def operation(active_token: CancellationToken) -> object:
        entered.set()
        while not active_token.is_set():
            active_token.wait(0.01)
        active_token.raise_if_cancelled()
        return object()

    worker = JobWorker(operation, token)
    thread = start_worker_thread(worker)
    assert entered.wait(timeout=1)

    with qtbot.waitSignal(worker.cancelled, timeout=1_000):
        worker.cancel()

    assert token.is_set()
    thread.quit()
    assert thread.wait(5_000)


def test_controller_maps_blocking_error_without_leaking_context() -> None:
    error = PipelineError(
        ErrorCode.OUTPUT_NOT_WRITABLE,
        "permission denied at /private/output",
        context={"path": "/private/output"},
    )

    message = user_message(error)

    assert message == ERROR_COPY["OutputNotWritable"]
    assert "/private/output" not in message


def test_progress_does_not_block_zero_delay_timer(qtbot) -> None:
    controller = DesktopController()
    fired: list[bool] = []
    QTimer.singleShot(0, lambda: fired.append(True))

    controller.handle_progress({"progress": 0.5})
    qtbot.waitUntil(lambda: bool(fired), timeout=1_000)


def test_close_requests_worker_cancellation(qtbot) -> None:
    controller = DesktopController()
    token = CancellationToken()
    worker = JobWorker(lambda active_token: active_token.wait(0.01), token)
    controller._worker = worker

    controller.request_cancel()

    assert token.is_set()
