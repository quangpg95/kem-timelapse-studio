from __future__ import annotations

from collections.abc import Callable, Iterable

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import Timeline, TimelineItem
from kem_timelapse.editing.commands import EditCommand, SetCrop, SetKeep, SetSpeed, SetWatermark

HistoryCallback = Callable[[Timeline], None]
_MAX_HISTORY = 100


class EditingSession:
    """Own immutable timeline snapshots while applying preview edits."""

    def __init__(self, timeline: Timeline, *, on_change: HistoryCallback | None = None) -> None:
        self._active = _copy_timeline(timeline)
        self._undo: list[Timeline] = []
        self._redo: list[Timeline] = []
        self._on_change = on_change

    def snapshot(self) -> Timeline:
        return _copy_timeline(self._active)

    def apply(self, command: EditCommand) -> Timeline:
        updated = _apply_command(self._active, command)
        self._push(self._undo, self._active)
        self._active = updated
        self._redo.clear()
        self._notify()
        return self.snapshot()

    def undo(self) -> Timeline:
        if not self._undo:
            return self.snapshot()
        self._push(self._redo, self._active)
        self._active = self._undo.pop()
        self._notify()
        return self.snapshot()

    def redo(self) -> Timeline:
        if not self._redo:
            return self.snapshot()
        self._push(self._undo, self._active)
        self._active = self._redo.pop()
        self._notify()
        return self.snapshot()

    def _push(self, history: list[Timeline], timeline: Timeline) -> None:
        history.append(_copy_timeline(timeline))
        if len(history) > _MAX_HISTORY:
            del history[0]

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change(self.snapshot())


def copy_shared_edits(source: Timeline, targets: Iterable[Timeline]) -> list[Timeline]:
    """Copy only shared keep/crop and watermark edits into independent timelines."""
    source_items = {(item.role, item.segment_id): item for item in source.items}
    copied: list[Timeline] = []
    for target in targets:
        changed = False
        items: list[TimelineItem] = []
        for item in target.items:
            shared = source_items.get((item.role, item.segment_id))
            if shared is None:
                items.append(item.model_copy(deep=True))
                continue
            if item.keep != shared.keep or item.crop_override != shared.crop_override:
                items.append(
                    item.model_copy(
                        update={
                            "keep": shared.keep,
                            "crop_override": shared.crop_override,
                        },
                        deep=True,
                    )
                )
                changed = True
            else:
                items.append(item.model_copy(deep=True))

        watermark_changed = (
            target.watermark_text != source.watermark_text
            or target.watermark_opacity != source.watermark_opacity
        )
        if changed or watermark_changed:
            copied.append(
                _validated_timeline(
                    target.model_copy(
                        update={
                            "items": items,
                            "watermark_text": source.watermark_text,
                            "watermark_opacity": source.watermark_opacity,
                            "revision": target.revision + 1,
                        },
                        deep=True,
                    )
                )
            )
        else:
            copied.append(_copy_timeline(target))
    return copied


def _apply_command(timeline: Timeline, command: EditCommand) -> Timeline:
    if isinstance(command, SetWatermark):
        return _validated_timeline(
            timeline.model_copy(
                update={
                    "watermark_text": command.text,
                    "watermark_opacity": command.opacity,
                    "revision": timeline.revision + 1,
                },
                deep=True,
            )
        )

    item_index = next(
        (index for index, item in enumerate(timeline.items) if item.id == command.item_id), None
    )
    if item_index is None:
        raise PipelineError(
            ErrorCode.TIMELINE_INVALID,
            "item is not present in timeline",
            context={"item_id": command.item_id},
        )

    item = timeline.items[item_index]
    update: dict[str, object]
    if isinstance(command, SetKeep):
        update = {"keep": command.keep}
    elif isinstance(command, SetSpeed):
        update = {"speed": command.speed}
    elif isinstance(command, SetCrop):
        update = {"crop_override": command.crop}
    else:
        raise AssertionError("unreachable edit command")
    items = [existing.model_copy(deep=True) for existing in timeline.items]
    items[item_index] = item.model_copy(update=update, deep=True)
    return _validated_timeline(
        timeline.model_copy(update={"items": items, "revision": timeline.revision + 1}, deep=True)
    )


def _copy_timeline(timeline: Timeline) -> Timeline:
    return _validated_timeline(timeline.model_copy(deep=True))


def _validated_timeline(timeline: Timeline) -> Timeline:
    return Timeline.model_validate(timeline.model_dump())
