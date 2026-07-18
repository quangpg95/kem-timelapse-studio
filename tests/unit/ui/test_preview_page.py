from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Qt

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Variant
from kem_timelapse.ui.preview_page import PreviewPage


def test_variant_switch_preserves_independent_edits(qtbot, editing_sessions) -> None:
    page = PreviewPage()
    qtbot.addWidget(page)
    page.set_sessions(editing_sessions)
    page.select_variant(Variant.TIKTOK_FAST)
    page.timeline_view.selectRow(0)
    page.speed_combo.setCurrentText("2×")
    assert editing_sessions[Variant.TIKTOK_FAST].snapshot().items[0].speed == 2
    assert editing_sessions[Variant.REELS_AESTHETIC].snapshot().items[0].speed != 2


def test_low_roi_confidence_blocks_render_until_manual_confirmation(qtbot) -> None:
    page = PreviewPage()
    qtbot.addWidget(page)
    page.set_warnings([WarningCode.LOW_ROI_CONFIDENCE])
    assert page.render_pack_button.isEnabled() is False
    page.roi_overlay.set_manual_points([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])
    qtbot.mouseClick(page.confirm_roi_button, Qt.LeftButton)
    assert page.render_pack_button.isEnabled() is True


@pytest.mark.parametrize(("label", "speed"), [("1×", 1), ("2×", 2), ("4×", 4), ("12×", 12)])
def test_all_approved_speeds_round_trip(qtbot, editing_sessions, label: str, speed: int) -> None:
    page = PreviewPage()
    qtbot.addWidget(page)
    page.set_sessions(editing_sessions)
    page.select_variant(Variant.TIKTOK_FAST)
    page.timeline_view.selectRow(0)
    page.speed_combo.setCurrentText(label)
    assert editing_sessions[Variant.TIKTOK_FAST].snapshot().items[0].speed == speed
    page.undo_button.click()
    assert editing_sessions[Variant.TIKTOK_FAST].snapshot().items[0].speed == 4
    page.redo_button.click()
    assert editing_sessions[Variant.TIKTOK_FAST].snapshot().items[0].speed == speed


def test_preview_defaults_and_stable_controls(qtbot) -> None:
    page = PreviewPage()
    qtbot.addWidget(page)
    assert page.watermark_text.text() == "@kem12032024"
    assert page.watermark_opacity.value() == 30
    assert {widget.objectName() for widget in page.findChildren(QObject)} >= {
        "variantTabs",
        "proxyVideo",
        "timelineView",
        "undoButton",
        "redoButton",
        "copyToAllButton",
        "confirmRoiButton",
        "renderFirstButton",
        "renderPackButton",
    }
