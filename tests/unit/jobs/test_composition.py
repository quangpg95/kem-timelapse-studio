from pathlib import Path

from kem_timelapse import cli
from kem_timelapse.composition import _ProductionStages, configure_cli
from kem_timelapse.domain.models import ProjectState, Variant
from kem_timelapse.jobs.runner import JobRunner
from kem_timelapse.storage.project_repository import ProjectRepository


def test_configure_cli_installs_concrete_job_runner_factory(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "project")
    repository.create(ProjectState(project_id="project", name="Painting"))
    repository.save_sources([])
    configure_cli()

    runner = cli._runner_for_project(repository.root)

    assert isinstance(runner, JobRunner)


def test_production_stages_validate_the_project_named_output_path(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "project")
    repository.create(ProjectState(project_id="project", name="Moon Painting"))
    stages = _ProductionStages(repository, overwrite=False)

    assert stages._output_path(Variant.TIKTOK_FAST).name == "moon-painting_tiktok-fast.mp4"
