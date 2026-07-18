from pathlib import Path

import pytest

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import JobStatus, ProjectState, Variant
from kem_timelapse.jobs.cancellation import CancellationToken
from kem_timelapse.jobs.runner import JobRunner, analysis_artifact_key
from kem_timelapse.storage.project_repository import ProjectRepository


class FakeStages:
    def __init__(self) -> None:
        self.rendered: list[Variant] = []
        self.analyzed: list[str] = []
        self.valid_analysis: set[str] = set()
        self.valid_outputs: set[Variant] = {Variant.TIKTOK_FAST}
        self.composed = False
        self.prepared_audio = False

    def prepare_audio(self) -> None:
        self.prepared_audio = True

    def selected_clip_ids(self) -> list[str]:
        return []

    def analysis_artifact_is_valid(self, clip_id: str) -> bool:
        return clip_id in self.valid_analysis

    def analyze_clip(self, clip_id: str, token: CancellationToken) -> None:
        token.raise_if_cancelled()
        self.analyzed.append(clip_id)
        self.valid_analysis.add(clip_id)

    def compose_timelines(self) -> None:
        self.composed = True

    def output_is_valid(self, variant: Variant) -> bool:
        return variant in self.valid_outputs or variant in self.rendered

    def render_variant(self, variant: Variant) -> None:
        self.rendered.append(variant)


def test_render_resume_skips_completed_tiktok(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "project")
    repository.create(
        ProjectState(
            project_id="p",
            name="Art",
            status=JobStatus.RENDERING,
            completed_variants=[Variant.TIKTOK_FAST],
        )
    )
    stages = FakeStages()
    JobRunner(repository, stages).render_pack()
    assert stages.rendered == [Variant.REELS_AESTHETIC, Variant.SHORTS_ASMR]
    assert repository.load_state().status is JobStatus.COMPLETED


def test_invalid_completed_output_is_rendered_again(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "project")
    repository.create(
        ProjectState(
            project_id="p",
            name="Art",
            status=JobStatus.RENDERING,
            completed_variants=[Variant.REELS_AESTHETIC],
        )
    )
    stages = FakeStages()

    JobRunner(repository, stages).render_pack()

    assert stages.rendered == list(Variant)
    assert repository.load_state().completed_variants == list(Variant)


def test_cancelled_analysis_records_resume_stage_and_reraises(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "project")
    repository.create(ProjectState(project_id="p", name="Art", status=JobStatus.INGESTED))
    token = CancellationToken()
    token.cancel()

    with pytest.raises(InterruptedError):
        JobRunner(repository, FakeStages(), token=token).analyze_to_review()

    state = repository.load_state()
    assert state.status is JobStatus.CANCELLED
    assert state.resume_from is JobStatus.ANALYZING


class FailingStages(FakeStages):
    def selected_clip_ids(self) -> list[str]:
        return ["clip-1"]

    def analyze_clip(self, clip_id: str, token: CancellationToken) -> None:
        raise PipelineError(
            ErrorCode.SOURCE_UNAVAILABLE,
            "source changed",
            context={"source_id": clip_id},
        )


def test_pipeline_failure_records_failed_state_and_preserves_error(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "project")
    repository.create(ProjectState(project_id="p", name="Art", status=JobStatus.INGESTED))

    with pytest.raises(PipelineError) as caught:
        JobRunner(repository, FailingStages()).analyze_to_review()

    assert caught.value.code is ErrorCode.SOURCE_UNAVAILABLE
    state = repository.load_state()
    assert state.status is JobStatus.FAILED
    assert state.resume_from is JobStatus.ANALYZING


def test_analysis_artifact_key_is_stable_and_tracks_roi_override() -> None:
    first = analysis_artifact_key(
        source_fingerprint="source",
        proxy_version="proxy-v1",
        analyzer_version="analyzer-v1",
        preset_version="preset-v1",
        roi_override={"center_x": 0.5, "center_y": 0.5, "scale": 1.0},
    )
    reordered = analysis_artifact_key(
        source_fingerprint="source",
        proxy_version="proxy-v1",
        analyzer_version="analyzer-v1",
        preset_version="preset-v1",
        roi_override={"scale": 1.0, "center_y": 0.5, "center_x": 0.5},
    )
    changed = analysis_artifact_key(
        source_fingerprint="source",
        proxy_version="proxy-v1",
        analyzer_version="analyzer-v1",
        preset_version="preset-v1",
        roi_override={"center_x": 0.6, "center_y": 0.5, "scale": 1.0},
    )

    assert first == reordered
    assert len(first) == 64
    assert changed != first
