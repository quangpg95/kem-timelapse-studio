from __future__ import annotations

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import JobStatus, ProjectState

ALLOWED: dict[JobStatus, set[JobStatus]] = {
    JobStatus.NEW: {JobStatus.INGESTED, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.INGESTED: {JobStatus.ANALYZING, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.ANALYZING: {JobStatus.REVIEW_READY, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.REVIEW_READY: {
        JobStatus.RENDERING,
        JobStatus.ANALYZING,
        JobStatus.CANCELLED,
    },
    JobStatus.RENDERING: {JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.CANCELLED: {JobStatus.ANALYZING, JobStatus.RENDERING},
    JobStatus.FAILED: {JobStatus.ANALYZING, JobStatus.RENDERING},
    JobStatus.COMPLETED: {JobStatus.RENDERING},
}


def transition(state: ProjectState, target: JobStatus) -> ProjectState:
    """Return a new project state after validating the explicit job graph."""
    if target not in ALLOWED[state.status]:
        raise PipelineError(
            ErrorCode.TIMELINE_INVALID,
            "invalid job state transition",
            context={"from": state.status.value, "to": target.value},
        )
    return state.model_copy(update={"status": target, "resume_from": None})
