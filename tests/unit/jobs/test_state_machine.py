import pytest

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import JobStatus, ProjectState
from kem_timelapse.jobs.state_machine import transition


def test_state_machine_accepts_happy_path_and_rejects_skip() -> None:
    state = ProjectState(project_id="p", name="Art", status=JobStatus.NEW)
    assert transition(state, JobStatus.INGESTED).status is JobStatus.INGESTED
    with pytest.raises(PipelineError) as caught:
        transition(state, JobStatus.RENDERING)
    assert caught.value.code is ErrorCode.TIMELINE_INVALID


def test_transition_returns_a_new_state_and_clears_resume_marker() -> None:
    state = ProjectState(
        project_id="p",
        name="Art",
        status=JobStatus.CANCELLED,
        resume_from=JobStatus.ANALYZING,
    )

    resumed = transition(state, JobStatus.ANALYZING)

    assert resumed.status is JobStatus.ANALYZING
    assert resumed.resume_from is None
    assert state.status is JobStatus.CANCELLED
