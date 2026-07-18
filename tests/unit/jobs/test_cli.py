import json
from pathlib import Path

from typer.testing import CliRunner

from kem_timelapse import cli
from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import JobStatus, ProjectState, Variant
from kem_timelapse.storage.project_repository import ProjectRepository


def test_inspect_prints_resumable_state_as_json(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "project")
    repository.create(
        ProjectState(
            project_id="p",
            name="Art",
            status=JobStatus.RENDERING,
            completed_analysis_clip_ids=["clip-1"],
            completed_variants=[Variant.TIKTOK_FAST],
            warning_codes=["TrackingLost"],
        )
    )

    result = CliRunner().invoke(cli.app, ["inspect", str(repository.root)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "Rendering",
        "resume_from": None,
        "completed_analysis_clip_ids": ["clip-1"],
        "completed_variants": ["tiktok-fast"],
        "warning_codes": ["TrackingLost"],
    }


def test_pipeline_error_uses_blocking_exit_code(monkeypatch, tmp_path: Path) -> None:
    class BrokenRunner:
        def render_pack(self) -> None:
            raise PipelineError(
                ErrorCode.TIMELINE_INVALID,
                "timeline missing",
                context={"variant": "tiktok-fast"},
            )

    monkeypatch.setattr(cli, "_runner_for_project", lambda *args, **kwargs: BrokenRunner())

    result = CliRunner().invoke(cli.app, ["render", str(tmp_path)])

    assert result.exit_code == 2
    assert "TimelineInvalid" in result.stderr
    assert "timeline missing" in result.stderr
