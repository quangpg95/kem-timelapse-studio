from kem_timelapse.ui.main_window import MainWindow


def test_window_starts_on_source_and_exposes_three_steps(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == "Kem Timelapse Studio"
    assert window.stack.currentWidget().objectName() == "sourcePage"
    assert [button.text() for button in window.step_buttons] == [
        "1. Nguồn quay",
        "2. Phân tích",
        "3. Preview & Render",
    ]
    assert window.analyze_button.isEnabled() is False


def test_source_drop_enables_analyze_after_validation(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    source = tmp_path / "clip.MOV"
    source.write_bytes(b"fixture")

    window.source_page.add_paths([source])

    assert window.analyze_button.isEnabled() is False
    window.source_page.set_probe_result(source, valid=True, summary="00:01 · 4K/30")

    assert window.source_page.source_count() == 1
    assert window.analyze_button.isEnabled() is True
