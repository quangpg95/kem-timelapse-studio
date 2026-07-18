"""Production composition root for the local desktop and diagnostic entry points."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from kem_timelapse.analysis.analyzer import HeuristicAnalyzer
from kem_timelapse.analysis.presets import BOOTSTRAP_PRESET
from kem_timelapse.analysis.roi import TrackedRoi
from kem_timelapse.analysis.segmenter import segment_windows
from kem_timelapse.audio.backends import DeepFilterBackend, FfmpegDenoiseBackend
from kem_timelapse.audio.models import AudioMixPlan
from kem_timelapse.audio.pipeline import AudioPipeline
from kem_timelapse.compose.composer import compose_timeline
from kem_timelapse.compose.presets import REELS, SHORTS, TIKTOK
from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import (
    JobStatus,
    ProjectState,
    Segment,
    SourceClip,
    Variant,
)
from kem_timelapse.framing.crop import plan_vertical_crop
from kem_timelapse.framing.models import FramingPlan
from kem_timelapse.framing.watermark import choose_watermark_placement
from kem_timelapse.ingest.service import IngestService
from kem_timelapse.jobs.cancellation import CancellationToken
from kem_timelapse.jobs.runner import JobRunner, analysis_artifact_key
from kem_timelapse.media.probe import MediaProbe
from kem_timelapse.media.process import CommandRunner
from kem_timelapse.media.proxy import ProxyBuilder
from kem_timelapse.render.manifest import sha256_file, write_manifest
from kem_timelapse.render.models import ManifestEntry
from kem_timelapse.render.renderer import Renderer, build_render_plan, output_filename
from kem_timelapse.render.validator import OutputValidator
from kem_timelapse.storage.atomic import atomic_write_json
from kem_timelapse.storage.project_repository import ProjectRepository


def configure_cli() -> None:
    """Install the concrete factory without making the core import the UI."""
    from kem_timelapse import cli

    cli.configure_runner_factory(create_job_runner)


def create_job_runner(
    project_dir: Path,
    sources: Sequence[Path] = (),
    overwrite: bool = False,
) -> JobRunner:
    repository = ProjectRepository(project_dir)
    services = _ProductionStages(repository, overwrite=overwrite)
    services.initialize(sources)
    return JobRunner(repository, services)


class _ProductionStages:
    """Small persistence adapter joining the independently-tested application services."""

    def __init__(self, repository: ProjectRepository, *, overwrite: bool) -> None:
        self._repository = repository
        self._overwrite = overwrite
        self._command_runner = CommandRunner()
        self._clips: list[SourceClip] = []
        self._audio_plans: dict[Variant, AudioMixPlan] = {}

    def initialize(self, paths: Sequence[Path]) -> None:
        if paths:
            clips = IngestService(MediaProbe(self._command_runner)).ingest(paths)
            existing_project = self._repository.root / "project.json"
            if existing_project.is_file():
                self._repository.save_sources(clips)
            else:
                self._repository.create(
                    ProjectState(
                        project_id=str(uuid.uuid4()),
                        name=self._repository.root.name or "Untitled painting",
                        status=JobStatus.INGESTED,
                    )
                )
                self._repository.save_sources(clips)
            self._clips = clips
            return
        self._clips = _load_sources(self._repository)

    def selected_clip_ids(self) -> Sequence[str]:
        return [clip.id for clip in self._clips if clip.selected]

    def analysis_artifact_is_valid(self, clip_id: str) -> bool:
        path = self._analysis_path(clip_id)
        if not path.is_file():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            clip = self._clip(clip_id)
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            return False
        return isinstance(payload, dict) and payload.get("artifact_key") == self._artifact_key(clip)

    def analyze_clip(self, clip_id: str, token: CancellationToken) -> None:
        clip = self._clip(clip_id)
        proxy = ProxyBuilder(self._command_runner).build(
            clip,
            self._repository.root / "cache/proxy",
            token,  # type: ignore[arg-type]
        )
        windows = HeuristicAnalyzer().analyze(proxy, lambda _timestamp: 0.0, token)
        segments = segment_windows(windows, BOOTSTRAP_PRESET)
        tracked = [
            TrackedRoi(
                timestamp_ms=item.start_ms,
                roi=item.roi,
                fallback="none" if item.roi else "center",
                warning=item.roi is None,
            )
            for item in windows
        ]
        atomic_write_json(
            self._analysis_path(clip_id),
            {
                "schema_version": 1,
                "artifact_key": self._artifact_key(clip),
                "proxy": proxy.model_dump(mode="json"),
                "windows": [item.model_dump(mode="json") for item in windows],
                "segments": [item.model_dump(mode="json") for item in segments],
                "tracked_roi": [item.model_dump(mode="json") for item in tracked],
            },
        )

    def compose_timelines(self) -> None:
        segments = self._segments()
        for preset in (TIKTOK, REELS, SHORTS):
            self._repository.save_timeline(compose_timeline(segments, preset))

    def prepare_audio(self) -> None:
        timelines = [self._repository.load_timeline(variant) for variant in Variant]
        pipeline = AudioPipeline(
            primary=DeepFilterBackend(),
            fallback=FfmpegDenoiseBackend(self._command_runner),
            runner=self._command_runner,  # type: ignore[arg-type]
        )
        segments = {segment.id: segment for segment in self._segments()}
        sources = {clip.id: clip for clip in self._clips}
        self._audio_plans = {
            variant: pipeline.prepare_variant(
                variant,
                timelines,
                segments,
                sources,
                self._repository.root / "cache/audio",
                music_path=None,
                rights_confirmed=False,
            )
            for variant in Variant
        }

    def output_is_valid(self, variant: Variant) -> bool:
        path = self._output_path(variant)
        try:
            OutputValidator().validate(path)
        except (OSError, PipelineError):
            return False
        return True

    def render_variant(self, variant: Variant) -> None:
        timeline = self._repository.load_timeline(variant)
        segments = {segment.id: segment for segment in self._segments()}
        sources = {clip.id: clip for clip in self._clips}
        framing = self._framing_plan()
        saliency: NDArray[np.float32] = np.zeros((12, 12), dtype=np.float32)
        watermark = choose_watermark_placement(
            saliency,
            canvas_box=(0.10, 0.10, 0.90, 0.90),
            text=timeline.watermark_text,
            opacity=timeline.watermark_opacity,
        )
        audio = self._audio_plans[variant]
        plan = build_render_plan(
            timeline,
            segments,
            sources,
            audio,
            framing,
            watermark,
            self._repository.root / "outputs",
            self._repository.load_state().name,
        )
        started = time.monotonic()
        probe = Renderer(self._command_runner, OutputValidator()).render(  # type: ignore[arg-type]
            plan, threading.Event(), overwrite=self._overwrite
        )
        write_manifest(
            self._repository.root,
            ManifestEntry(
                variant=variant,
                filename=plan.final_path.name,
                sha256=sha256_file(plan.final_path),
                timeline_revision=timeline.revision,
                elapsed_seconds=time.monotonic() - started,
                probe=probe,
                warning_codes=plan.warning_codes,
                source_fingerprints={clip.id: clip.fingerprint for clip in self._clips},
                analyzer_version=BOOTSTRAP_PRESET.version,
                composer_version="composer-v1",
                audio_preset_version=AudioPipeline.PRESET_VERSION,
            ),
        )

    def _framing_plan(self) -> FramingPlan:
        first = self._clips[0]
        samples = [
            TrackedRoi.model_validate(item)
            for payload in self._analysis_payloads()
            for item in payload["tracked_roi"]
        ]
        if not samples:
            raise PipelineError(ErrorCode.TIMELINE_INVALID, "no ROI samples", context={})
        return plan_vertical_crop(samples, first.media.width, first.media.height)

    def _segments(self) -> list[Segment]:
        return [
            Segment.model_validate(item)
            for payload in self._analysis_payloads()
            for item in payload["segments"]
        ]

    def _analysis_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for clip in self._clips:
            if not clip.selected:
                continue
            path = self._analysis_path(clip.id)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise PipelineError(
                    ErrorCode.TIMELINE_INVALID,
                    "analysis results are unavailable",
                    context={"clip_id": clip.id},
                ) from error
            if not isinstance(payload, dict):
                raise PipelineError(
                    ErrorCode.TIMELINE_INVALID,
                    "analysis results have an invalid schema",
                    context={"clip_id": clip.id},
                )
            payloads.append(payload)
        return payloads

    def _clip(self, clip_id: str) -> SourceClip:
        return next(clip for clip in self._clips if clip.id == clip_id)

    def _analysis_path(self, clip_id: str) -> Path:
        return self._repository.root / "analysis" / f"{clip_id}.json"

    def _output_path(self, variant: Variant) -> Path:
        name = self._repository.load_state().name
        return self._repository.root / "outputs" / output_filename(name, variant)

    @staticmethod
    def _artifact_key(clip: SourceClip) -> str:
        return analysis_artifact_key(
            source_fingerprint=clip.fingerprint,
            proxy_version=ProxyBuilder.VERSION,
            analyzer_version=BOOTSTRAP_PRESET.version,
            preset_version=BOOTSTRAP_PRESET.version,
            roi_override=None,
        )


def _load_sources(repository: ProjectRepository) -> list[SourceClip]:
    try:
        payload = json.loads((repository.root / "sources.json").read_text(encoding="utf-8"))
        source_values = payload["sources"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise PipelineError(
            ErrorCode.SOURCE_UNAVAILABLE,
            "project does not contain imported sources",
            context={"project": repository.root.name},
        ) from error
    return [SourceClip.model_validate(item) for item in source_values]
