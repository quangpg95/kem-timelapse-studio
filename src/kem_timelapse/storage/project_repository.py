from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kem_timelapse.domain.models import ProjectState, SourceClip, Timeline, Variant
from kem_timelapse.storage.atomic import atomic_write_json


class ProjectRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self, state: ProjectState) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for relative in ("analysis", "timelines", "cache/proxy", "cache/audio", "outputs", "logs"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self.save_state(state)

    def save_state(self, state: ProjectState) -> None:
        atomic_write_json(self.root / "project.json", state.model_dump(mode="json"))

    def load_state(self) -> ProjectState:
        return ProjectState.model_validate_json((self.root / "project.json").read_text())

    def save_sources(self, sources: Sequence[SourceClip]) -> None:
        atomic_write_json(
            self.root / "sources.json",
            {"schema_version": 1, "sources": [item.model_dump(mode="json") for item in sources]},
        )

    def save_timeline(self, timeline: Timeline) -> None:
        atomic_write_json(
            self.root / "timelines" / f"{timeline.variant.value}.json",
            timeline.model_dump(mode="json"),
        )

    def load_timeline(self, variant: Variant) -> Timeline:
        path = self.root / "timelines" / f"{variant.value}.json"
        return Timeline.model_validate_json(path.read_text())
