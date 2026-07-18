from __future__ import annotations

from PySide6.QtCore import Qt

from kem_timelapse.domain.models import Variant
from kem_timelapse.editing.commands import SetKeep, SetSpeed
from kem_timelapse.ui.timeline_model import TimelineTableModel


def test_timeline_model_emits_commands_without_mutating_session(editing_sessions) -> None:
    session = editing_sessions[Variant.TIKTOK_FAST]
    commands: list[object] = []
    model = TimelineTableModel(session.snapshot(), segment_lookup={}, on_edit=commands.append)
    keep_index = model.index(0, model.KEEP_COLUMN)
    speed_index = model.index(0, model.SPEED_COLUMN)
    assert model.rowCount() == 1
    assert model.flags(keep_index) & Qt.ItemIsUserCheckable
    assert model.flags(speed_index) & Qt.ItemIsEditable
    assert model.setData(keep_index, Qt.Unchecked, Qt.CheckStateRole)
    assert model.setData(speed_index, 2, Qt.EditRole)
    assert commands == [
        SetKeep(item_id="tiktok-fast-body-shared-0", keep=False),
        SetSpeed(item_id="tiktok-fast-body-shared-0", speed=2),
    ]
    assert session.snapshot().items[0].keep is True
    assert session.snapshot().items[0].speed == 4
