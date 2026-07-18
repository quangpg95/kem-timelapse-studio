import threading

from PySide6.QtCore import QThread, QTimer

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import Timeline, TimelineItem, Variant
from kem_timelapse.editing.session import EditingSession
from kem_timelapse.jobs.cancellation import CancellationToken
from kem_timelapse.ui.controller import ERROR_COPY, DesktopController, user_message
from kem_timelapse.ui.main_window import MainWindow
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


def test_controller_debounces_preview_timeline_persistence(qtbot) -> None:
    class Repository:
        def __init__(self) -> None:
            self.saved: list[Timeline] = []

        def save_timeline(self, timeline: Timeline) -> None:
            self.saved.append(timeline)

    repository = Repository()
    window = MainWindow()
    qtbot.addWidget(window)
    controller = DesktopController(repository=repository)
    controller.attach(window)
    sessions = {
        variant: EditingSession(
            Timeline(
                variant=variant,
                revision=0,
                audio_mode="asmr",
                items=[
                    TimelineItem(
                        id=f"{variant.value}-item",
                        role="body",
                        segment_id="shared",
                        trim_in_ms=0,
                        trim_out_ms=1_000,
                        speed=4,
                    )
                ],
            )
        )
        for variant in Variant
    }
    controller.set_editing_sessions(sessions)
    window.preview_page.select_variant(Variant.TIKTOK_FAST)
    window.preview_page.timeline_view.selectRow(0)
    window.preview_page.speed_combo.setCurrentText("2×")

    qtbot.waitUntil(lambda: len(repository.saved) == 3, timeout=1_000)
    assert repository.saved[0].items[0].speed == 2


def test_preview_render_persists_timelines_before_starting_tiktok_operation(qtbot) -> None:
    class Repository:
        def __init__(self) -> None:
            self.saved: list[Timeline] = []

        def save_timeline(self, timeline: Timeline) -> None:
            self.saved.append(timeline)

    repository = Repository()
    saved_at_start: list[int] = []
    window = MainWindow()
    qtbot.addWidget(window)
    controller = DesktopController(
        repository=repository,
        render_pack_operation=lambda _: saved_at_start.append(len(repository.saved)),
        output_writable=lambda: True,
    )
    controller.attach(window)
    controller.set_editing_sessions(_sessions())

    window.preview_page.render_first_button.click()

    qtbot.waitUntil(lambda: bool(saved_at_start), timeout=1_000)
    assert [timeline.variant for timeline in repository.saved] == list(Variant)
    assert saved_at_start == [3]


def test_preview_render_controls_gate_missing_timelines_unwritable_output_and_active_worker(
    qtbot,
) -> None:
    class Repository:
        def save_timeline(self, timeline: Timeline) -> None:
            pass

    writable = False
    window = MainWindow()
    qtbot.addWidget(window)
    controller = DesktopController(
        repository=Repository(),
        render_pack_operation=lambda _: None,
        output_writable=lambda: writable,
    )
    controller.attach(window)
    assert window.preview_page.render_first_button.isEnabled() is False
    assert window.preview_page.render_pack_button.isEnabled() is False

    controller.set_editing_sessions(_sessions())
    assert window.preview_page.render_first_button.isEnabled() is False

    writable = True
    controller.refresh_render_controls()
    assert window.preview_page.render_first_button.isEnabled() is True
    assert window.preview_page.render_pack_button.isEnabled() is True

    controller._worker = JobWorker(lambda _: None, CancellationToken())
    controller.refresh_render_controls()
    assert window.preview_page.render_first_button.isEnabled() is False
    assert window.preview_page.render_pack_button.isEnabled() is False


def test_preview_render_pack_signal_uses_injected_operation(qtbot) -> None:
    class Repository:
        def save_timeline(self, timeline: Timeline) -> None:
            pass

    calls: list[CancellationToken] = []
    window = MainWindow()
    qtbot.addWidget(window)
    controller = DesktopController(
        repository=Repository(),
        render_pack_operation=lambda token: calls.append(token),
        output_writable=lambda: True,
    )
    controller.attach(window)
    controller.set_editing_sessions(_sessions())

    window.preview_page.render_pack_button.click()

    qtbot.waitUntil(lambda: bool(calls), timeout=1_000)


def _sessions() -> dict[Variant, EditingSession]:
    return {
        variant: EditingSession(
            Timeline(
                variant=variant,
                revision=0,
                audio_mode="asmr",
                items=[
                    TimelineItem(
                        id=f"{variant.value}-item",
                        role="body",
                        segment_id="shared",
                        trim_in_ms=0,
                        trim_out_ms=1_000,
                        speed=4,
                    )
                ],
            )
        )
        for variant in Variant
    }
