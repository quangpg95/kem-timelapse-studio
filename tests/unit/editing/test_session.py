from pathlib import Path

import pytest

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import CropOverride, ProjectState, Timeline, TimelineItem, Variant
from kem_timelapse.editing.commands import SetCrop, SetKeep, SetSpeed, SetWatermark
from kem_timelapse.editing.session import EditingSession, copy_shared_edits
from kem_timelapse.storage.project_repository import ProjectRepository


def timeline(variant: Variant) -> Timeline:
    return Timeline(
        variant=variant,
        revision=0,
        audio_mode="asmr_music",
        items=[
            TimelineItem(
                id="body-shared",
                role="body",
                segment_id="shared",
                trim_in_ms=0,
                trim_out_ms=4_000,
                speed=4,
            ),
            TimelineItem(
                id="body-private",
                role="body",
                segment_id="private",
                trim_in_ms=4_000,
                trim_out_ms=8_000,
                speed=4,
            ),
        ],
    )


def test_apply_undo_redo_are_immutable() -> None:
    original = timeline(Variant.TIKTOK_FAST)
    session = EditingSession(original)

    changed = session.apply(SetSpeed(item_id="body-shared", speed=2))

    assert original.items[0].speed == 4
    assert changed.items[0].speed == 2 and changed.revision == 1
    assert session.undo().items[0].speed == 4
    assert session.redo().items[0].speed == 2


def test_copy_to_all_only_updates_segments_present_in_targets() -> None:
    source = EditingSession(timeline(Variant.TIKTOK_FAST)).apply(
        SetKeep(item_id="body-shared", keep=False)
    )
    target = timeline(Variant.REELS_AESTHETIC)

    copied = copy_shared_edits(source, [target])[0]

    assert copied.variant is Variant.REELS_AESTHETIC
    assert copied.items[0].keep is False
    assert copied.items[1].keep is True
    assert copied.revision == 1


def test_copy_to_all_copies_crop_and_watermark_without_copying_speed_or_trim() -> None:
    source = EditingSession(timeline(Variant.TIKTOK_FAST)).apply(
        SetCrop(item_id="body-shared", crop=CropOverride(center_x=0.4, center_y=0.6, scale=1.2))
    )
    source = EditingSession(source).apply(SetWatermark(text="@kem", opacity=0.5))
    target = timeline(Variant.SHORTS_ASMR)

    copied = copy_shared_edits(source, [target])[0]

    assert copied.items[0].crop_override == CropOverride(center_x=0.4, center_y=0.6, scale=1.2)
    assert copied.items[0].speed == 4
    assert copied.items[0].trim_in_ms == 0
    assert copied.watermark_text == "@kem"
    assert copied.watermark_opacity == 0.5
    assert copied.audio_mode == target.audio_mode


def test_missing_item_is_rejected_without_changing_history() -> None:
    session = EditingSession(timeline(Variant.TIKTOK_FAST))

    with pytest.raises(PipelineError) as caught:
        session.apply(SetKeep(item_id="not-present", keep=False))

    assert caught.value.code is ErrorCode.TIMELINE_INVALID
    assert caught.value.context == {"item_id": "not-present"}
    assert session.snapshot().revision == 0
    assert session.undo().revision == 0


def test_accepted_revisions_are_persisted_and_rejected_commands_are_not(tmp_path: Path) -> None:
    repo = ProjectRepository(tmp_path / "artwork")
    repo.create(ProjectState(project_id="project-1", name="Artwork"))
    persisted: list[int] = []

    def save(timeline_to_save: Timeline) -> None:
        persisted.append(timeline_to_save.revision)
        repo.save_timeline(timeline_to_save)

    session = EditingSession(timeline(Variant.TIKTOK_FAST), on_change=save)
    session.apply(SetKeep(item_id="body-shared", keep=False))
    session.undo()
    session.redo()
    with pytest.raises(PipelineError):
        session.apply(SetKeep(item_id="not-present", keep=False))

    assert persisted == [1, 0, 1]
    assert repo.load_timeline(Variant.TIKTOK_FAST).revision == 1
