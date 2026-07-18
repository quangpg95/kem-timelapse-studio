from pathlib import Path

from kem_timelapse.domain.models import JobStatus, ProjectState
from kem_timelapse.storage.project_repository import ProjectRepository


def test_create_builds_project_layout_and_round_trips_state(tmp_path: Path) -> None:
    repo = ProjectRepository(tmp_path / "artwork")
    state = ProjectState(project_id="p-1", name="Sea", status=JobStatus.NEW)

    repo.create(state)

    loaded = repo.load_state()
    assert loaded == state
    assert {"analysis", "timelines", "cache", "outputs", "logs"} <= {
        path.name for path in repo.root.iterdir() if path.is_dir()
    }
