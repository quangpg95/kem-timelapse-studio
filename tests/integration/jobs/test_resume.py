from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from kem_timelapse.domain.models import JobStatus, ProjectState, Variant
from kem_timelapse.jobs.cancellation import CancellationToken
from kem_timelapse.jobs.runner import JobRunner
from kem_timelapse.storage.fingerprint import fingerprint_source
from kem_timelapse.storage.project_repository import ProjectRepository


class SimulatedCrash(BaseException):
    pass


def crash_after(expected_name: str) -> Callable[[str], None]:
    fired = False

    def hook(name: str) -> None:
        nonlocal fired
        if name == expected_name and not fired:
            fired = True
            raise SimulatedCrash(name)

    return hook


def source_snapshot(path: Path) -> tuple[int, int, str]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, fingerprint_source(path)


class CountingStages:
    def __init__(self, repository: ProjectRepository, source_paths: list[Path]) -> None:
        self.repository = repository
        self.source_paths = source_paths
        self.analysis_calls: list[str] = []
        self.render_calls: list[Variant] = []

    def selected_clip_ids(self) -> list[str]:
        return ["clip-1", "clip-2"]

    def analysis_artifact_is_valid(self, clip_id: str) -> bool:
        path = self.repository.root / "analysis" / f"{clip_id}.json"
        if not path.exists():
            return False
        return path.read_text(encoding="utf-8") == '{"schema_version": 1}\n'

    def analyze_clip(self, clip_id: str, token: CancellationToken) -> None:
        token.raise_if_cancelled()
        self.analysis_calls.append(clip_id)
        path = self.repository.root / "analysis" / f"{clip_id}.json"
        partial = path.with_suffix(".partial.json")
        partial.write_text('{"schema_version": 1}\n', encoding="utf-8")
        os.replace(partial, path)

    def compose_timelines(self) -> None:
        for variant in Variant:
            path = self.repository.root / "timelines" / f"{variant.value}.json"
            path.write_text('{"schema_version": 1}\n', encoding="utf-8")

    def prepare_audio(self) -> None:
        return None

    def output_is_valid(self, variant: Variant) -> bool:
        path = self.repository.root / "outputs" / f"painting_{variant.value}.mp4"
        return path.is_file() and path.read_bytes() == b"validated"

    def render_variant(self, variant: Variant) -> None:
        self.render_calls.append(variant)
        final = self.repository.root / "outputs" / f"painting_{variant.value}.mp4"
        partial = final.with_name(f"{final.stem}.partial.mp4")
        partial.write_bytes(b"validated")
        os.replace(partial, final)


@pytest.fixture
def resumable_project(
    tmp_path: Path,
) -> tuple[ProjectRepository, list[tuple[int, int, str]], CountingStages]:
    source_paths = [tmp_path / "clip-1.mov", tmp_path / "clip-2.mov"]
    for index, path in enumerate(source_paths):
        path.write_bytes(f"source-{index}".encode())
    repository = ProjectRepository(tmp_path / "project")
    repository.create(ProjectState(project_id="p", name="Art", status=JobStatus.INGESTED))
    snapshots = [source_snapshot(path) for path in source_paths]
    return repository, snapshots, CountingStages(repository, source_paths)


def test_resume_after_analysis_and_tiktok_checkpoints(
    resumable_project: tuple[ProjectRepository, list[tuple[int, int, str]], CountingStages],
) -> None:
    repository, sources_before, counting_stages = resumable_project
    with pytest.raises(SimulatedCrash):
        JobRunner(
            repository,
            counting_stages,
            checkpoint_hook=crash_after("analysis:clip-1"),
        ).analyze_to_review()
    JobRunner(repository, counting_stages).analyze_to_review()
    assert counting_stages.analysis_calls.count("clip-1") == 1

    with pytest.raises(SimulatedCrash):
        JobRunner(
            repository,
            counting_stages,
            checkpoint_hook=crash_after("render:tiktok-fast"),
        ).render_pack()
    abandoned_partial = repository.root / "outputs" / "abandoned.partial.mp4"
    abandoned_partial.write_bytes(b"partial")
    JobRunner(repository, counting_stages).render_pack()
    assert counting_stages.render_calls.count(Variant.TIKTOK_FAST) == 1
    assert repository.load_state().status is JobStatus.COMPLETED
    assert all(counting_stages.output_is_valid(variant) for variant in Variant)
    assert not abandoned_partial.exists()
    assert [source_snapshot(path) for path in counting_stages.source_paths] == sources_before
