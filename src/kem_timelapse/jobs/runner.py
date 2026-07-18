from __future__ import annotations

import hashlib
import json
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import JobStatus, ProjectState, Variant
from kem_timelapse.jobs.cancellation import CancellationToken
from kem_timelapse.jobs.events import JobEvent, JsonlEventSink
from kem_timelapse.jobs.state_machine import transition
from kem_timelapse.storage.project_repository import ProjectRepository

VARIANT_ORDER: tuple[Variant, ...] = (
    Variant.TIKTOK_FAST,
    Variant.REELS_AESTHETIC,
    Variant.SHORTS_ASMR,
)


def analysis_artifact_key(
    *,
    source_fingerprint: str,
    proxy_version: str,
    analyzer_version: str,
    preset_version: str,
    roi_override: object,
) -> str:
    """Hash every input that can change a persisted per-clip analysis artifact."""
    payload = {
        "source_fingerprint": source_fingerprint,
        "proxy_version": proxy_version,
        "analyzer_version": analyzer_version,
        "preset_version": preset_version,
        "roi_override": roi_override,
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class JobStages(Protocol):
    def selected_clip_ids(self) -> Sequence[str]: ...

    def analysis_artifact_is_valid(self, clip_id: str) -> bool: ...

    def analyze_clip(self, clip_id: str, token: CancellationToken) -> None: ...

    def compose_timelines(self) -> None: ...

    def prepare_audio(self) -> None: ...

    def output_is_valid(self, variant: Variant) -> bool: ...

    def render_variant(self, variant: Variant) -> None: ...


@dataclass
class PipelineStages:
    """Concrete adapter that wires application services behind the JobStages boundary."""

    clip_ids: Callable[[], Sequence[str]]
    validate_analysis: Callable[[str], bool]
    analyze: Callable[[str, CancellationToken], None]
    compose: Callable[[], None]
    audio: Callable[[], None]
    validate_output: Callable[[Variant], bool]
    render: Callable[[Variant], None]

    def selected_clip_ids(self) -> Sequence[str]:
        return self.clip_ids()

    def analysis_artifact_is_valid(self, clip_id: str) -> bool:
        return self.validate_analysis(clip_id)

    def analyze_clip(self, clip_id: str, token: CancellationToken) -> None:
        self.analyze(clip_id, token)

    def compose_timelines(self) -> None:
        self.compose()

    def prepare_audio(self) -> None:
        self.audio()

    def output_is_valid(self, variant: Variant) -> bool:
        return self.validate_output(variant)

    def render_variant(self, variant: Variant) -> None:
        self.render(variant)


class JobRunner:
    def __init__(
        self,
        repository: ProjectRepository,
        stages: JobStages,
        token: CancellationToken | None = None,
        checkpoint_hook: Callable[[str], None] | None = None,
        event_sink: JsonlEventSink | None = None,
    ) -> None:
        self._repository = repository
        self._stages = stages
        self._token = token or CancellationToken()
        self._checkpoint_hook = checkpoint_hook
        self._events = event_sink or JsonlEventSink(repository.root / "logs" / "jobs.jsonl")

    def analyze_to_review(self) -> None:
        active_stage = JobStatus.ANALYZING
        state = self._repository.load_state()
        try:
            state = self._enter_stage(state, active_stage)
            self._cleanup_partials("analysis")
            clip_ids = list(self._stages.selected_clip_ids())
            state = self._invalidate_analysis_checkpoints(state, clip_ids)
            total = max(1, len(clip_ids))
            for index, clip_id in enumerate(clip_ids):
                if (
                    clip_id in state.completed_analysis_clip_ids
                    and self._stages.analysis_artifact_is_valid(clip_id)
                ):
                    continue
                self._token.raise_if_cancelled()
                self._stages.analyze_clip(clip_id, self._token)
                self._token.raise_if_cancelled()
                if not self._stages.analysis_artifact_is_valid(clip_id):
                    raise PipelineError(
                        ErrorCode.OUTPUT_VALIDATION_FAILED,
                        "analysis artifact is invalid",
                        context={"clip_id": clip_id},
                    )
                completed = list(dict.fromkeys([*state.completed_analysis_clip_ids, clip_id]))
                state = state.model_copy(update={"completed_analysis_clip_ids": completed})
                self._repository.save_state(state)
                self._emit(
                    state,
                    "analysis_checkpoint",
                    clip_id=clip_id,
                    progress=(index + 1) / total,
                )
                self._checkpoint(f"analysis:{clip_id}")
            self._token.raise_if_cancelled()
            self._stages.compose_timelines()
            state = transition(state, JobStatus.REVIEW_READY)
            self._repository.save_state(state)
            self._emit(state, "review_ready", progress=1.0)
        except InterruptedError:
            self._cleanup_partials()
            self._persist_terminal(state, JobStatus.CANCELLED, active_stage)
            raise
        except PipelineError as error:
            self._persist_terminal(state, JobStatus.FAILED, active_stage, error=error)
            raise
        except Exception:
            self._persist_terminal(
                state,
                JobStatus.FAILED,
                active_stage,
                details={"traceback": traceback.format_exc()},
            )
            raise

    def render_pack(self) -> None:
        active_stage = JobStatus.RENDERING
        state = self._repository.load_state()
        try:
            state = self._enter_stage(state, active_stage)
            self._cleanup_partials("outputs")
            state = self._invalidate_render_checkpoints(state)
            self._token.raise_if_cancelled()
            self._stages.prepare_audio()
            for index, variant in enumerate(VARIANT_ORDER):
                if (
                    variant in state.completed_variants
                    and self._stages.output_is_valid(variant)
                ):
                    continue
                self._token.raise_if_cancelled()
                self._stages.render_variant(variant)
                self._token.raise_if_cancelled()
                if not self._stages.output_is_valid(variant):
                    raise PipelineError(
                        ErrorCode.OUTPUT_VALIDATION_FAILED,
                        "rendered output is invalid",
                        context={"variant": variant.value},
                    )
                completed = list(dict.fromkeys([*state.completed_variants, variant]))
                state = state.model_copy(update={"completed_variants": completed})
                self._repository.save_state(state)
                self._emit(
                    state,
                    "render_checkpoint",
                    variant=variant,
                    progress=(index + 1) / len(VARIANT_ORDER),
                )
                self._checkpoint(f"render:{variant.value}")
            if not all(
                variant in state.completed_variants and self._stages.output_is_valid(variant)
                for variant in VARIANT_ORDER
            ):
                raise PipelineError(
                    ErrorCode.OUTPUT_VALIDATION_FAILED,
                    "Content Pack is incomplete",
                    context={"completed": [item.value for item in state.completed_variants]},
                )
            state = transition(state, JobStatus.COMPLETED)
            self._repository.save_state(state)
            self._emit(state, "completed", progress=1.0)
        except InterruptedError:
            self._cleanup_partials()
            self._persist_terminal(state, JobStatus.CANCELLED, active_stage)
            raise
        except PipelineError as error:
            self._persist_terminal(state, JobStatus.FAILED, active_stage, error=error)
            raise
        except Exception:
            self._persist_terminal(
                state,
                JobStatus.FAILED,
                active_stage,
                details={"traceback": traceback.format_exc()},
            )
            raise

    def _enter_stage(self, state: ProjectState, active: JobStatus) -> ProjectState:
        if state.status is active:
            entered = state.model_copy(update={"resume_from": None})
        else:
            entered = transition(state, active)
        self._repository.save_state(entered)
        self._emit(entered, "started", progress=0.0)
        return entered

    def _invalidate_analysis_checkpoints(
        self,
        state: ProjectState,
        selected_clip_ids: Sequence[str],
    ) -> ProjectState:
        selected = set(selected_clip_ids)
        valid = [
            clip_id
            for clip_id in state.completed_analysis_clip_ids
            if clip_id in selected and self._stages.analysis_artifact_is_valid(clip_id)
        ]
        if valid == state.completed_analysis_clip_ids:
            return state
        updated = state.model_copy(update={"completed_analysis_clip_ids": valid})
        self._repository.save_state(updated)
        return updated

    def _invalidate_render_checkpoints(self, state: ProjectState) -> ProjectState:
        valid = [
            variant
            for variant in VARIANT_ORDER
            if variant in state.completed_variants and self._stages.output_is_valid(variant)
        ]
        if valid == state.completed_variants:
            return state
        updated = state.model_copy(update={"completed_variants": valid})
        self._repository.save_state(updated)
        return updated

    def _persist_terminal(
        self,
        state: ProjectState,
        target: JobStatus,
        resume_from: JobStatus,
        *,
        error: PipelineError | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        terminal = state.model_copy(update={"status": target, "resume_from": resume_from})
        self._repository.save_state(terminal)
        payload: dict[str, object] = dict(details or {})
        if error is not None:
            payload.update(error.context)
        self._emit(
            terminal,
            target.value.lower(),
            progress=0.0,
            error=error,
            details=payload,
        )

    def _emit(
        self,
        state: ProjectState,
        event: str,
        *,
        progress: float,
        clip_id: str | None = None,
        variant: Variant | None = None,
        error: PipelineError | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._events.emit(
            JobEvent(
                project_id=state.project_id,
                stage=state.status.value,
                event=event,
                clip_id=clip_id,
                variant=variant,
                progress=progress,
                error_code=error.code if error is not None else None,
                details=dict(details or {}),
            )
        )

    def _checkpoint(self, name: str) -> None:
        if self._checkpoint_hook is not None:
            self._checkpoint_hook(name)

    def _cleanup_partials(self, relative: str | None = None) -> None:
        root = self._repository.root / relative if relative is not None else self._repository.root
        if not root.exists():
            return
        for pattern in ("*.partial", "*.partial.*"):
            for path in root.rglob(pattern):
                if path.is_file():
                    path.unlink(missing_ok=True)
