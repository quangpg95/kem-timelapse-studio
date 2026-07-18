# Kem Timelapse Studio MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local macOS desktop application that analyzes one 1–3 hour iPhone painting recording once and renders a three-video, platform-tailored vertical Content Pack with editable pacing, ASMR audio, tracked framing, watermarking, checkpoint/resume, and measurable acceptance results.

**Architecture:** Keep a typed, UI-independent Python core organized around versioned project artifacts: ingest → proxy → feature windows → canonical segments → three timelines → audio/framing plans → validated renders. PySide6 only calls application services; all FFmpeg/ffprobe and DeepFilterNet work is behind injected adapters, so unit tests use fakes and media integration tests use small committed fixtures. Every long stage writes an atomic checkpoint and can resume without modifying source media.

**Tech Stack:** Python 3.10+, PySide6, Pydantic 2, OpenCV, NumPy, pydub, optional DeepFilterNet, FFmpeg/ffprobe with `h264_videotoolbox`, pytest/pytest-qt, Ruff, mypy, PyInstaller.

## Global Constraints

- Target macOS Apple Silicon; acceptance hardware is Mac M3 Pro with at least 24 GB RAM.
- Standard source is iPhone 15 Pro Max MOV/MP4, 4K, 30 fps, SDR, one file or ordered multi-clip folder, total duration 1–3 hours.
- Runtime is Python 3.10+; code must not use Python 3.11-only APIs such as `enum.StrEnum`.
- The pipeline is local-only: no network calls, no telemetry, no cloud dependencies.
- Source files are immutable. Never open a source for writing, delete it, change metadata, or render in place.
- Allowed timeline speeds are exactly 1×, 2×, 4×, and 12×.
- Render three MP4 outputs in order: TikTok Fast 25–35 s, Reels Aesthetic 35–50 s, Shorts ASMR 55–90 s.
- Every output is H.264/AAC, 1080×1920, constant 30 fps, `yuv420p`; silent variants receive a silent AAC track.
- Use `@kem12032024` at 30% opacity unless the user changes it in preview.
- DeepFilterNet runs only on selected source ranges; fallback is FFmpeg denoise with warning `AudioDenoiseDegraded`.
- Benchmark gates: remove at least 80% labeled inactivity, retain at least 90% labeled important detail, A/V drift below 100 ms, first output at most 15 minutes, full pack at most 20 minutes on acceptance hardware.
- Do not add 16:9 4K output, social posting, multi-track editing, model training, cloud sync, or retention guarantees.
- Follow TDD for every behavior: demonstrate the focused test failing, implement the minimum behavior, demonstrate it passing, run the task regression set, then commit.

---

## Delivery slices and file map

The MVP is one integrated product because every later stage consumes the same `SourceClip`, `Segment`, `Timeline`, and `ProjectState` contracts. Tasks are grouped into four reviewable slices:

1. **Foundation and ingest (Tasks 1–4):** package, domain schema, atomic project storage, source probing, preflight, and proxies.
2. **Analysis and editorial decisions (Tasks 5–9):** ROI, visual/audio features, segmentation, composers, and non-destructive timeline edits.
3. **Media production and reliability (Tasks 10–13):** ASMR, framing, rendering/validation, job state/resume, and internal CLI.
4. **Desktop and acceptance (Tasks 14–17):** three-step UI, preview controls, golden/E2E benchmark, and unsigned `.app` packaging.

Planned package ownership:

```text
pyproject.toml                         dependencies, entry points, test/lint config
src/kem_timelapse/domain/              stable typed models and error codes
src/kem_timelapse/storage/             fingerprints, atomic JSON, project layout
src/kem_timelapse/media/               subprocess, ffprobe, proxy and FFmpeg adapters
src/kem_timelapse/ingest/              ordering and preflight
src/kem_timelapse/analysis/            ROI, feature extraction and segmentation
src/kem_timelapse/compose/             platform presets and timeline composers
src/kem_timelapse/editing/             immutable edit commands and undo/redo
src/kem_timelapse/audio/               selected-range stems, denoise and mix plans
src/kem_timelapse/framing/             crop smoothing and watermark placement
src/kem_timelapse/render/              filter graphs, encode, validate and manifest
src/kem_timelapse/jobs/                state machine, checkpoints, cancellation, logs
src/kem_timelapse/ui/                  PySide6 views and controller only
src/kem_timelapse/cli.py               diagnostic/internal CLI over the same services
tests/unit/                             pure, fast tests without external binaries
tests/integration/                     small generated/committed media fixtures
tests/e2e/                              acceptance recording and benchmark harness
```

### Task 1: Package skeleton and stable domain contracts

**Files:**
- Create: `pyproject.toml`
- Create: `src/kem_timelapse/__init__.py`
- Create: `src/kem_timelapse/domain/models.py`
- Create: `src/kem_timelapse/domain/errors.py`
- Create: `tests/unit/domain/test_models.py`
- Create: `tests/unit/domain/test_errors.py`

**Interfaces:**
- Consumes: no application code; only Pydantic and Python standard library.
- Produces: `Variant`, `SegmentKind`, `JobStatus`, `Point`, `Roi`, `MediaInfo`, `SourceClip`, `FeatureWindow`, `Segment`, `CropOverride`, `TimelineItem`, `Timeline`, `ProjectState`, `ErrorCode`, `WarningCode`, and `PipelineError`.

- [ ] **Step 1: Create packaging metadata and the failing domain tests**

Create `pyproject.toml` with these exact dependency groups and tool settings:

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "kem-timelapse"
version = "0.1.0"
description = "Local painting timelapse and ASMR Content Pack studio"
requires-python = ">=3.10"
dependencies = [
  "numpy>=1.26",
  "opencv-python-headless>=4.10",
  "platformdirs>=4.2",
  "pydantic>=2.7",
  "pydub>=0.25",
  "PySide6>=6.7",
  "typer>=0.12",
]

[project.optional-dependencies]
deepfilter = ["deepfilternet>=0.5"]
dev = [
  "mypy>=1.10",
  "pyinstaller>=6.8",
  "pytest>=8.2",
  "pytest-cov>=5.0",
  "pytest-qt>=4.4",
  "ruff>=0.5",
]

[project.scripts]
kem-timelapse = "kem_timelapse.cli:app"
kem-timelapse-desktop = "kem_timelapse.ui.app:main"

[tool.hatch.build.targets.wheel]
packages = ["src/kem_timelapse"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
  "media: requires ffmpeg and ffprobe",
  "deepfilter: requires the optional DeepFilterNet backend",
  "e2e: requires the private acceptance recording",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.10"
strict = true
packages = ["kem_timelapse"]
```

Create tests that establish validation and stable external values:

```python
# tests/unit/domain/test_models.py
from pathlib import Path

import pytest
from pydantic import ValidationError

from kem_timelapse.domain.models import Segment, SegmentKind, Timeline, TimelineItem, Variant


def make_segment() -> Segment:
    return Segment(
        id="seg-1",
        source_id="clip-1",
        start_ms=1_000,
        end_ms=5_000,
        kind=SegmentKind.DETAIL,
        activity_score=0.8,
        detail_score=0.9,
        audio_score=0.6,
        roi_confidence=0.95,
        recommended_speed=2,
        keep_default=True,
        reason_codes=["detail_high"],
    )


def test_segment_rejects_reversed_range() -> None:
    values = make_segment().model_dump()
    values.update(start_ms=5_000, end_ms=1_000)
    with pytest.raises(ValidationError, match="end_ms must be greater"):
        Segment.model_validate(values)


def test_timeline_item_rejects_noncanonical_speed() -> None:
    with pytest.raises(ValidationError):
        TimelineItem(id="item-1", role="body", segment_id="seg-1", trim_in_ms=0, trim_out_ms=1_000, speed=3)


def test_variant_slug_is_stable() -> None:
    assert Variant.TIKTOK_FAST.value == "tiktok-fast"
    assert Path(f"painting_{Variant.SHORTS_ASMR.value}.mp4").name == "painting_shorts-asmr.mp4"


def test_timeline_rejects_duplicate_item_ids() -> None:
    item = TimelineItem(id="same", role="body", segment_id="seg-1", trim_in_ms=0, trim_out_ms=1_000, speed=1)
    with pytest.raises(ValidationError, match="item ids must be unique"):
        Timeline(variant=Variant.TIKTOK_FAST, revision=0, audio_mode="asmr", items=[item, item])
```

```python
# tests/unit/domain/test_errors.py
from kem_timelapse.domain.errors import ErrorCode, PipelineError, WarningCode


def test_pipeline_error_exposes_stable_code_and_context() -> None:
    error = PipelineError(
        ErrorCode.SOURCE_UNAVAILABLE,
        "Source cannot be read",
        context={"source_id": "clip-1"},
    )
    assert error.code.value == "SourceUnavailable"
    assert error.context == {"source_id": "clip-1"}
    assert WarningCode.TRACKING_LOST.value == "TrackingLost"
```

- [ ] **Step 2: Create the environment and prove the tests fail before package code exists**

Run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest tests/unit/domain -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'kem_timelapse.domain'`.

- [ ] **Step 3: Implement the complete domain enums, models, and error type**

Implement `src/kem_timelapse/domain/errors.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    SOURCE_UNAVAILABLE = "SourceUnavailable"
    INSUFFICIENT_DISK = "InsufficientDisk"
    RENDER_BACKEND_UNAVAILABLE = "RenderBackendUnavailable"
    OUTPUT_NOT_WRITABLE = "OutputNotWritable"
    TIMELINE_INVALID = "TimelineInvalid"
    OUTPUT_VALIDATION_FAILED = "OutputValidationFailed"


class WarningCode(str, Enum):
    LOW_ROI_CONFIDENCE = "LowRoiConfidence"
    AUDIO_DENOISE_DEGRADED = "AudioDenoiseDegraded"
    NO_SOURCE_AUDIO = "NoSourceAudio"
    TRACKING_LOST = "TrackingLost"
    WATERMARK_PLACEMENT_FALLBACK = "WatermarkPlacementFallback"


class PipelineError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str, *, context: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.context = context
```

Implement `src/kem_timelapse/domain/models.py` with the exact serialized field names used by every later task:

```python
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Speed = Literal[1, 2, 4, 12]


class Variant(str, Enum):
    TIKTOK_FAST = "tiktok-fast"
    REELS_AESTHETIC = "reels-aesthetic"
    SHORTS_ASMR = "shorts-asmr"


class SegmentKind(str, Enum):
    INACTIVE = "inactive"
    BROAD_FILL = "broad_fill"
    PROGRESS = "progress"
    DETAIL = "detail"
    ASMR_PEAK = "asmr_peak"
    HOOK_CANDIDATE = "hook_candidate"
    REVEAL_CANDIDATE = "reveal_candidate"


class JobStatus(str, Enum):
    NEW = "New"
    INGESTED = "Ingested"
    ANALYZING = "Analyzing"
    REVIEW_READY = "ReviewReady"
    RENDERING = "Rendering"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class Point(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class Roi(BaseModel):
    points: tuple[Point, Point, Point, Point]
    confidence: float = Field(ge=0.0, le=1.0)
    manual: bool = False


class MediaInfo(BaseModel):
    duration_ms: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps_num: int = Field(gt=0)
    fps_den: int = Field(gt=0)
    codec: str
    rotation_deg: Literal[0, 90, 180, 270] = 0
    has_audio: bool
    creation_time: str | None = None


class SourceClip(BaseModel):
    id: str
    path: Path
    size_bytes: int = Field(gt=0)
    mtime_ns: int = Field(gt=0)
    fingerprint: str
    media: MediaInfo
    order: int = Field(ge=0)
    selected: bool = True


class FeatureWindow(BaseModel):
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    motion_score: float = Field(ge=0.0, le=1.0)
    canvas_change_score: float = Field(ge=0.0, le=1.0)
    changed_area_score: float = Field(ge=0.0, le=1.0)
    detail_score: float = Field(ge=0.0, le=1.0)
    audio_score: float = Field(ge=0.0, le=1.0)
    roi: Roi | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "FeatureWindow":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class Segment(BaseModel):
    id: str
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    kind: SegmentKind
    activity_score: float = Field(ge=0.0, le=1.0)
    detail_score: float = Field(ge=0.0, le=1.0)
    audio_score: float = Field(ge=0.0, le=1.0)
    roi_confidence: float = Field(ge=0.0, le=1.0)
    recommended_speed: Speed
    keep_default: bool
    reason_codes: list[str]

    @model_validator(mode="after")
    def validate_range(self) -> "Segment":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class CropOverride(BaseModel):
    center_x: float = Field(ge=0.0, le=1.0)
    center_y: float = Field(ge=0.0, le=1.0)
    scale: float = Field(gt=0.0, le=4.0)


class TimelineItem(BaseModel):
    id: str
    role: Literal["hook", "body", "reveal"]
    segment_id: str
    trim_in_ms: int = Field(ge=0)
    trim_out_ms: int = Field(gt=0)
    speed: Speed
    keep: bool = True
    crop_override: CropOverride | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "TimelineItem":
        if self.trim_out_ms <= self.trim_in_ms:
            raise ValueError("trim_out_ms must be greater than trim_in_ms")
        return self


class Timeline(BaseModel):
    schema_version: int = 1
    variant: Variant
    revision: int = Field(ge=0)
    audio_mode: Literal["asmr_music", "asmr", "music", "silent"]
    watermark_text: str = "@kem12032024"
    watermark_opacity: float = Field(default=0.30, ge=0.0, le=1.0)
    items: list[TimelineItem]

    @model_validator(mode="after")
    def validate_unique_item_ids(self) -> "Timeline":
        item_ids = [item.id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("timeline item ids must be unique")
        return self


class ProjectState(BaseModel):
    schema_version: int = 1
    project_id: str
    name: str
    status: JobStatus = JobStatus.NEW
    resume_from: JobStatus | None = None
    completed_analysis_clip_ids: list[str] = Field(default_factory=list)
    completed_variants: list[Variant] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
```

Create an empty `src/kem_timelapse/__init__.py` and `__init__.py` files in each package directory when the directory first appears.

- [ ] **Step 4: Run focused tests, lint, and type checking**

Run:

```bash
.venv/bin/pytest tests/unit/domain -q
.venv/bin/ruff check src/kem_timelapse/domain tests/unit/domain
.venv/bin/mypy src/kem_timelapse/domain
```

Expected: 5 tests pass; Ruff reports no errors; mypy exits 0.

- [ ] **Step 5: Commit the domain foundation**

```bash
git add pyproject.toml src/kem_timelapse tests/unit/domain
git commit -m "feat: define core media and timeline contracts"
```

### Task 2: Atomic project storage and source fingerprinting

**Files:**
- Create: `src/kem_timelapse/storage/atomic.py`
- Create: `src/kem_timelapse/storage/fingerprint.py`
- Create: `src/kem_timelapse/storage/project_repository.py`
- Create: `tests/unit/storage/test_atomic.py`
- Create: `tests/unit/storage/test_fingerprint.py`
- Create: `tests/unit/storage/test_project_repository.py`

**Interfaces:**
- Consumes: `ProjectState`, `SourceClip`, `Timeline`, `Variant` from Task 1.
- Produces: `atomic_write_json(path: Path, value: object) -> None`, `fingerprint_source(path: Path, chunk_bytes: int = 8_388_608) -> str`, and `ProjectRepository` methods `create`, `load_state`, `save_state`, `save_sources`, `save_timeline`, `load_timeline`.

- [ ] **Step 1: Write failing tests for atomic replacement, fingerprint invalidation, and layout**

```python
# tests/unit/storage/test_atomic.py
import json
from pathlib import Path

from kem_timelapse.storage.atomic import atomic_write_json


def test_atomic_write_replaces_json_and_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "project.json"
    atomic_write_json(target, {"revision": 1})
    atomic_write_json(target, {"revision": 2})
    assert json.loads(target.read_text()) == {"revision": 2}
    assert list(tmp_path.glob(".project.json.*.tmp")) == []
```

```python
# tests/unit/storage/test_fingerprint.py
from pathlib import Path

from kem_timelapse.storage.fingerprint import fingerprint_source


def test_fingerprint_changes_when_tail_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.mov"
    source.write_bytes(b"a" * 64 + b"tail-a")
    before = fingerprint_source(source, chunk_bytes=16)
    source.write_bytes(b"a" * 64 + b"tail-b")
    after = fingerprint_source(source, chunk_bytes=16)
    assert before != after
```

```python
# tests/unit/storage/test_project_repository.py
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
```

- [ ] **Step 2: Run the storage tests and confirm import failures**

Run: `.venv/bin/pytest tests/unit/storage -q`

Expected: collection fails because `kem_timelapse.storage` does not exist.

- [ ] **Step 3: Implement atomic JSON and fast source fingerprints**

```python
# src/kem_timelapse/storage/atomic.py
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
```

```python
# src/kem_timelapse/storage/fingerprint.py
from __future__ import annotations

import hashlib
from pathlib import Path


def fingerprint_source(path: Path, chunk_bytes: int = 8_388_608) -> str:
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(f"{stat.st_size}:{stat.st_mtime_ns}:".encode())
    with path.open("rb") as stream:
        head = stream.read(chunk_bytes)
        digest.update(head)
        if stat.st_size > chunk_bytes:
            stream.seek(max(0, stat.st_size - chunk_bytes))
            digest.update(stream.read(chunk_bytes))
    return digest.hexdigest()
```

- [ ] **Step 4: Implement the versioned project repository**

```python
# src/kem_timelapse/storage/project_repository.py
from __future__ import annotations

from pathlib import Path
from typing import Sequence

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
```

- [ ] **Step 5: Run focused and regression checks**

Run:

```bash
.venv/bin/pytest tests/unit/storage tests/unit/domain -q
.venv/bin/ruff check src/kem_timelapse/storage tests/unit/storage
.venv/bin/mypy src/kem_timelapse/storage
```

Expected: all tests pass and both static checks exit 0.

- [ ] **Step 6: Commit atomic project persistence**

```bash
git add src/kem_timelapse/storage tests/unit/storage
git commit -m "feat: persist resumable project artifacts atomically"
```

### Task 3: Safe process runner, ffprobe ingest, and preflight

**Files:**
- Create: `src/kem_timelapse/media/process.py`
- Create: `src/kem_timelapse/media/probe.py`
- Create: `src/kem_timelapse/ingest/service.py`
- Create: `src/kem_timelapse/ingest/preflight.py`
- Create: `tests/unit/media/test_probe.py`
- Create: `tests/unit/ingest/test_service.py`
- Create: `tests/unit/ingest/test_preflight.py`

**Interfaces:**
- Consumes: `MediaInfo`, `SourceClip`, `PipelineError`, `ErrorCode`, `fingerprint_source`.
- Produces: `CompletedCommand`, `CommandRunner.run(args, cancel_event)`, `MediaProbe.probe(path)`, `IngestService.ingest(paths)`, and `Preflight.check(project_root, estimated_bytes)`.

- [ ] **Step 1: Write failing parsing, ordering, and preflight tests**

```python
# tests/unit/media/test_probe.py
import json
from pathlib import Path

from kem_timelapse.media.probe import MediaProbe
from kem_timelapse.media.process import CompletedCommand


class FakeRunner:
    def run(self, args: list[str], cancel_event: object | None = None) -> CompletedCommand:
        payload = {
            "format": {"duration": "3.5", "tags": {"creation_time": "2026-01-02T03:04:05Z"}},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "width": 3840,
                    "height": 2160,
                    "avg_frame_rate": "30000/1001",
                    "side_data_list": [{"rotation": -90}],
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        return CompletedCommand(0, json.dumps(payload), "")


def test_probe_normalizes_rotation_and_audio(tmp_path: Path) -> None:
    source = tmp_path / "clip with spaces.MOV"
    source.write_bytes(b"media")
    info = MediaProbe(FakeRunner()).probe(source)
    assert (info.duration_ms, info.rotation_deg, info.has_audio) == (3_500, 270, True)
    assert (info.fps_num, info.fps_den) == (30_000, 1_001)
```

```python
# tests/unit/ingest/test_service.py
from pathlib import Path

from kem_timelapse.domain.models import MediaInfo
from kem_timelapse.ingest.service import IngestService


class FakeProbe:
    def probe(self, path: Path) -> MediaInfo:
        creation = "2026-01-02T00:00:00Z" if path.name == "b.MOV" else None
        return MediaInfo(
            duration_ms=1_000,
            width=3840,
            height=2160,
            fps_num=30,
            fps_den=1,
            codec="hevc",
            rotation_deg=0,
            has_audio=True,
            creation_time=creation,
        )


def test_ingest_orders_creation_time_then_filename(tmp_path: Path) -> None:
    a = tmp_path / "a.MOV"
    b = tmp_path / "b.MOV"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    clips = IngestService(FakeProbe()).ingest([a, b])
    assert [clip.path.name for clip in clips] == ["b.MOV", "a.MOV"]
    assert [clip.order for clip in clips] == [0, 1]
```

```python
# tests/unit/ingest/test_preflight.py
from pathlib import Path

import pytest

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.ingest.preflight import Preflight


def test_preflight_reports_required_and_available_disk(tmp_path: Path) -> None:
    check = Preflight(binary_lookup=lambda name: f"/usr/local/bin/{name}", free_bytes=lambda path: 99)
    with pytest.raises(PipelineError) as caught:
        check.check(tmp_path, estimated_bytes=100)
    assert caught.value.code is ErrorCode.INSUFFICIENT_DISK
    assert caught.value.context == {"required_bytes": 100, "available_bytes": 99}
```

- [ ] **Step 2: Run the focused tests and confirm missing-module failures**

Run: `.venv/bin/pytest tests/unit/media/test_probe.py tests/unit/ingest -q`

Expected: collection fails for missing `kem_timelapse.media` and `kem_timelapse.ingest`.

- [ ] **Step 3: Implement the subprocess boundary and ffprobe parser**

Implement a runner that always receives an argument sequence and never `shell=True`:

```python
# src/kem_timelapse/media/process.py
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class CompletedCommand:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    def run(
        self,
        args: Sequence[str],
        cancel_event: threading.Event | None = None,
    ) -> CompletedCommand:
        process = subprocess.Popen(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        while process.poll() is None:
            if cancel_event is not None and cancel_event.wait(0.05):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise InterruptedError("command cancelled")
        stdout, stderr = process.communicate()
        return CompletedCommand(process.returncode, stdout, stderr)
```

```python
# src/kem_timelapse/media/probe.py
from __future__ import annotations

import json
import threading
from fractions import Fraction
from pathlib import Path
from typing import Protocol, Sequence

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import MediaInfo
from kem_timelapse.media.process import CompletedCommand


class Runner(Protocol):
    def run(
        self,
        args: Sequence[str],
        cancel_event: threading.Event | None = None,
    ) -> CompletedCommand:
        raise NotImplementedError


class MediaProbe:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def probe(self, path: Path) -> MediaInfo:
        result = self._runner.run([
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ])
        if result.returncode != 0:
            raise PipelineError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "ffprobe could not read source",
                context={"path": str(path), "stderr": result.stderr[-500:]},
            )
        payload = json.loads(result.stdout)
        video = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
        audio = any(stream["codec_type"] == "audio" for stream in payload["streams"])
        fps = Fraction(video.get("avg_frame_rate", "30/1"))
        rotation = 0
        for side_data in video.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = int(side_data["rotation"]) % 360
        tags = payload.get("format", {}).get("tags", {})
        return MediaInfo(
            duration_ms=round(float(payload["format"]["duration"]) * 1_000),
            width=int(video["width"]),
            height=int(video["height"]),
            fps_num=fps.numerator,
            fps_den=fps.denominator,
            codec=str(video["codec_name"]),
            rotation_deg=rotation,
            has_audio=audio,
            creation_time=tags.get("creation_time"),
        )
```

The protocol method may use an ellipsis body because it is a static interface declaration, not an unfinished implementation.

- [ ] **Step 4: Implement deterministic ingest and blocking preflight errors**

`IngestService.ingest` must resolve paths, reject missing files, probe each source, fingerprint it, sort by parsed creation time with filename as stable fallback, assign deterministic IDs from the first 16 fingerprint characters, and never open a source in write mode. `Preflight.check` must verify `ffmpeg`, `ffprobe`, output writability, `h264_videotoolbox` in `ffmpeg -encoders`, required filters `drawtext`, `loudnorm`, and `sidechaincompress` in `ffmpeg -filters`, plus required disk bytes. Use dependency-injected `binary_lookup` and `free_bytes` so tests never depend on the developer machine.

Add this public shape:

```python
class IngestService:
    def __init__(self, probe: MediaProbe) -> None:
        self._probe = probe

    def ingest(self, paths: Sequence[Path]) -> list[SourceClip]:
        resolved = [path.expanduser().resolve(strict=True) for path in paths]
        records = [(path, self._probe.probe(path), fingerprint_source(path)) for path in resolved]
        records.sort(key=lambda item: (item[1].creation_time is None, item[1].creation_time or "", item[0].name))
        return [
            SourceClip(
                id=f"clip-{fingerprint[:16]}",
                path=path,
                size_bytes=path.stat().st_size,
                mtime_ns=path.stat().st_mtime_ns,
                fingerprint=fingerprint,
                media=media,
                order=order,
            )
            for order, (path, media, fingerprint) in enumerate(records)
        ]
```

Use `os.access(project_root, os.W_OK)`, `shutil.which`, `shutil.disk_usage(project_root).free`, and an encoder probe through `CommandRunner` in the concrete preflight implementation. Every failure must raise the exact `ErrorCode` from Task 1 and include actionable numeric/path context.

- [ ] **Step 5: Run tests and static checks**

Run:

```bash
.venv/bin/pytest tests/unit/media/test_probe.py tests/unit/ingest -q
.venv/bin/ruff check src/kem_timelapse/media src/kem_timelapse/ingest tests/unit/media tests/unit/ingest
.venv/bin/mypy src/kem_timelapse/media src/kem_timelapse/ingest
```

Expected: all focused tests pass; Ruff and mypy exit 0.

- [ ] **Step 6: Commit the ingest boundary**

```bash
git add src/kem_timelapse/media src/kem_timelapse/ingest tests/unit/media tests/unit/ingest
git commit -m "feat: probe and validate source recordings safely"
```

### Task 4: Timestamp-preserving analysis proxies

**Files:**
- Create: `src/kem_timelapse/media/proxy.py`
- Create: `tests/unit/media/test_proxy.py`
- Create: `tests/integration/media/test_proxy_ffmpeg.py`
- Create: `tests/fixtures/.gitkeep`

**Interfaces:**
- Consumes: `SourceClip`, `CommandRunner`, project `cache/proxy` path, cancellation event.
- Produces: `ProxyArtifact(source_id: str, path: Path, width: int, height: int, fps: int, duration_ms: int, cache_key: str)` and `ProxyBuilder.build(clip, cache_dir, cancel_event)`.

- [ ] **Step 1: Write a failing unit test for safe proxy arguments and cache reuse**

```python
# tests/unit/media/test_proxy.py
from pathlib import Path

from kem_timelapse.domain.models import MediaInfo, SourceClip
from kem_timelapse.media.process import CompletedCommand
from kem_timelapse.media.proxy import ProxyBuilder


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, args: list[str], cancel_event: object | None = None) -> CompletedCommand:
        self.calls.append(args)
        Path(args[-1]).write_bytes(b"proxy")
        return CompletedCommand(0, "", "")


def test_proxy_uses_argument_list_and_reuses_valid_cache(tmp_path: Path) -> None:
    source = tmp_path / "clip with spaces.MOV"
    source.write_bytes(b"source")
    clip = SourceClip(
        id="clip-1",
        path=source,
        size_bytes=6,
        mtime_ns=source.stat().st_mtime_ns,
        fingerprint="abc",
        media=MediaInfo(
            duration_ms=10_000, width=3840, height=2160, fps_num=30, fps_den=1,
            codec="hevc", rotation_deg=0, has_audio=True,
        ),
        order=0,
    )
    runner = RecordingRunner()
    builder = ProxyBuilder(runner)
    first = builder.build(clip, tmp_path / "cache", None)
    second = builder.build(clip, tmp_path / "cache", None)
    assert first == second
    assert len(runner.calls) == 1
    assert str(source) in runner.calls[0]
    assert "scale=-2:720,fps=10,format=yuv420p" in runner.calls[0]
```

- [ ] **Step 2: Run the unit test and confirm the missing module failure**

Run: `.venv/bin/pytest tests/unit/media/test_proxy.py -q`

Expected: collection fails because `kem_timelapse.media.proxy` does not exist.

- [ ] **Step 3: Implement proxy cache keys and atomic FFmpeg output**

```python
# src/kem_timelapse/media/proxy.py
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Protocol, Sequence

from pydantic import BaseModel

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.domain.models import SourceClip
from kem_timelapse.media.process import CompletedCommand


class ProxyArtifact(BaseModel):
    source_id: str
    path: Path
    width: int
    height: int
    fps: int = 10
    duration_ms: int
    cache_key: str


class Runner(Protocol):
    def run(
        self,
        args: Sequence[str],
        cancel_event: threading.Event | None = None,
    ) -> CompletedCommand:
        raise NotImplementedError


class ProxyBuilder:
    VERSION = "proxy-v1-720p10"

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def build(
        self,
        clip: SourceClip,
        cache_dir: Path,
        cancel_event: threading.Event | None,
    ) -> ProxyArtifact:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = f"{clip.fingerprint}-{self.VERSION}"
        final_path = cache_dir / f"{clip.id}-{cache_key[-18:]}.mp4"
        artifact = ProxyArtifact(
            source_id=clip.id,
            path=final_path,
            width=720 if clip.media.rotation_deg in (90, 270) else 1280,
            height=1280 if clip.media.rotation_deg in (90, 270) else 720,
            duration_ms=clip.media.duration_ms,
            cache_key=cache_key,
        )
        if final_path.is_file() and final_path.stat().st_size > 0:
            return artifact
        temporary = final_path.with_suffix(".partial.mp4")
        scale_filter = (
            "scale=720:-2,fps=10,format=yuv420p"
            if clip.media.rotation_deg in (90, 270)
            else "scale=-2:720,fps=10,format=yuv420p"
        )
        result = self._runner.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(clip.path),
            "-map", "0:v:0", "-an", "-vf", scale_filter,
            "-c:v", "h264_videotoolbox", "-b:v", "2M", "-movflags", "+faststart",
            str(temporary),
        ], cancel_event)
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            raise PipelineError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "proxy generation failed",
                context={"source_id": clip.id, "stderr": result.stderr[-500:]},
            )
        os.replace(temporary, final_path)
        return artifact
```

- [ ] **Step 4: Add a real-media integration test generated by FFmpeg**

The integration test must create a 2-second 3840×2160/30 synthetic color source with a 1 kHz AAC tone in `tmp_path`, call the concrete `ProxyBuilder`, then use `MediaProbe` to assert 1280×720, 10 fps within fraction tolerance, two-second duration within 100 ms, and no audio stream. Mark it `@pytest.mark.media`; skip with an explicit reason when `ffmpeg`, `ffprobe`, or `h264_videotoolbox` is unavailable.

Use this fixture command as an argument list:

```python
[
    "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=3840x2160:r=30:d=2",
    "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:duration=2",
    "-c:v", "hevc_videotoolbox", "-c:a", "aac", str(source),
]
```

- [ ] **Step 5: Run unit tests, then the media test when the backend exists**

Run:

```bash
.venv/bin/pytest tests/unit/media/test_proxy.py -q
.venv/bin/pytest tests/integration/media/test_proxy_ffmpeg.py -m media -q
.venv/bin/ruff check src/kem_timelapse/media/proxy.py tests/unit/media/test_proxy.py tests/integration/media/test_proxy_ffmpeg.py
```

Expected: unit test passes; integration test either passes or reports one intentional backend skip, never an unexplained failure.

- [ ] **Step 6: Commit proxy generation**

```bash
git add src/kem_timelapse/media/proxy.py tests/unit/media/test_proxy.py tests/integration/media/test_proxy_ffmpeg.py tests/fixtures/.gitkeep
git commit -m "feat: generate reusable timestamp-aligned proxies"
```

### Task 5: Canvas ROI detection and loss-tolerant tracking

**Files:**
- Create: `src/kem_timelapse/analysis/roi.py`
- Create: `tests/unit/analysis/test_roi.py`
- Create: `tests/fixtures/images/canvas-rectangle.png`

**Interfaces:**
- Consumes: BGR NumPy frames in display orientation and domain `Point`/`Roi`.
- Produces: `detect_canvas_roi(frame: NDArray[np.uint8]) -> Roi | None`, `TrackedRoi(timestamp_ms, roi, fallback, warning)`, and `RoiTracker.update(timestamp_ms, observation)`.

- [ ] **Step 1: Write failing synthetic detection and tracker fallback tests**

```python
# tests/unit/analysis/test_roi.py
import cv2
import numpy as np

from kem_timelapse.analysis.roi import RoiTracker, detect_canvas_roi


def canvas_frame() -> np.ndarray:
    frame = np.full((720, 1280, 3), 35, dtype=np.uint8)
    cv2.rectangle(frame, (220, 110), (1060, 650), (245, 245, 245), thickness=-1)
    cv2.rectangle(frame, (220, 110), (1060, 650), (120, 120, 120), thickness=8)
    return frame


def test_detect_canvas_returns_normalized_clockwise_quad() -> None:
    roi = detect_canvas_roi(canvas_frame())
    assert roi is not None
    assert roi.confidence >= 0.70
    assert abs(roi.points[0].x - 220 / 1280) < 0.03
    assert abs(roi.points[0].y - 110 / 720) < 0.03


def test_tracker_holds_then_centers_after_loss() -> None:
    detected = detect_canvas_roi(canvas_frame())
    assert detected is not None
    tracker = RoiTracker(alpha=0.25, hold_ms=1_000)
    assert tracker.update(0, detected).fallback == "none"
    assert tracker.update(500, None).fallback == "hold"
    lost = tracker.update(1_500, None)
    assert lost.fallback == "center"
    assert lost.warning is True
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv/bin/pytest tests/unit/analysis/test_roi.py -q`

Expected: collection fails because `kem_timelapse.analysis.roi` is missing.

- [ ] **Step 3: Implement quadrilateral detection and normalized point ordering**

Use Canny edges, external contours, `approxPolyDP`, convexity, area ratio, and rectangularity. Reject candidates below 8% of the frame. Score confidence as half rectangularity and half normalized area coverage. Order points top-left, top-right, bottom-right, bottom-left by sum/difference coordinates and divide by frame width/height before constructing `Roi`.

The complete public implementation shape is:

```python
from __future__ import annotations

from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from kem_timelapse.domain.models import Point, Roi


class TrackedRoi(BaseModel):
    timestamp_ms: int
    roi: Roi | None
    fallback: Literal["none", "hold", "center"]
    warning: bool


def _ordered(points: NDArray[np.float32]) -> NDArray[np.float32]:
    result = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    result[0] = points[np.argmin(sums)]
    result[2] = points[np.argmax(sums)]
    result[1] = points[np.argmin(differences)]
    result[3] = points[np.argmax(differences)]
    return result


def detect_canvas_roi(frame: NDArray[np.uint8]) -> Roi | None:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[float, NDArray[np.float32]]] = []
    frame_area = float(width * height)
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        area = float(abs(cv2.contourArea(polygon)))
        if area / frame_area < 0.08:
            continue
        rectangle = cv2.minAreaRect(polygon)
        box_area = max(1.0, float(rectangle[1][0] * rectangle[1][1]))
        rectangularity = min(1.0, area / box_area)
        confidence = 0.5 * rectangularity + 0.5 * min(1.0, (area / frame_area) / 0.30)
        candidates.append((confidence, polygon.reshape(4, 2).astype(np.float32)))
    if not candidates:
        return None
    confidence, pixels = max(candidates, key=lambda item: item[0])
    points = _ordered(pixels)
    normalized = tuple(Point(x=float(x / width), y=float(y / height)) for x, y in points)
    return Roi(points=normalized, confidence=confidence)
```

- [ ] **Step 4: Implement smoothing, hold-last, and center fallback**

`RoiTracker` stores the last accepted ROI/time. On a new observation, exponential-smooth each normalized point with `alpha`. On missing observation within `hold_ms`, return the last ROI with confidence multiplied by 0.8 and fallback `hold`. Beyond `hold_ms`, return `roi=None`, fallback `center`, warning true. A manual ROI bypasses smoothing and becomes the new stable state.

Use this constructor and method signature exactly:

```python
class RoiTracker:
    def __init__(self, *, alpha: float = 0.25, hold_ms: int = 1_000) -> None:
        self._alpha = alpha
        self._hold_ms = hold_ms
        self._last: Roi | None = None
        self._last_seen_ms: int | None = None

    def update(self, timestamp_ms: int, observation: Roi | None) -> TrackedRoi:
        if observation is not None:
            if self._last is not None and not observation.manual:
                points = tuple(
                    Point(
                        x=self._alpha * current.x + (1 - self._alpha) * previous.x,
                        y=self._alpha * current.y + (1 - self._alpha) * previous.y,
                    )
                    for current, previous in zip(observation.points, self._last.points)
                )
                observation = Roi(points=points, confidence=observation.confidence)
            self._last = observation
            self._last_seen_ms = timestamp_ms
            return TrackedRoi(timestamp_ms=timestamp_ms, roi=observation, fallback="none", warning=False)
        if self._last is not None and self._last_seen_ms is not None:
            if timestamp_ms - self._last_seen_ms <= self._hold_ms:
                held = self._last.model_copy(update={"confidence": self._last.confidence * 0.8})
                return TrackedRoi(timestamp_ms=timestamp_ms, roi=held, fallback="hold", warning=False)
        return TrackedRoi(timestamp_ms=timestamp_ms, roi=None, fallback="center", warning=True)
```

- [ ] **Step 5: Generate the stable image fixture and run checks**

Generate `tests/fixtures/images/canvas-rectangle.png` once from `canvas_frame()` using `cv2.imwrite`, then make the test read the committed image as an additional regression case. Run:

```bash
.venv/bin/pytest tests/unit/analysis/test_roi.py -q
.venv/bin/ruff check src/kem_timelapse/analysis/roi.py tests/unit/analysis/test_roi.py
.venv/bin/mypy src/kem_timelapse/analysis/roi.py
```

Expected: both behavior tests and the fixture regression pass; static checks exit 0.

- [ ] **Step 6: Commit canvas ROI detection**

```bash
git add src/kem_timelapse/analysis/roi.py tests/unit/analysis/test_roi.py tests/fixtures/images/canvas-rectangle.png
git commit -m "feat: detect and track painting canvas ROI"
```

### Task 6: Two-pass visual and brush-audio feature extraction

**Files:**
- Create: `src/kem_timelapse/analysis/features.py`
- Create: `src/kem_timelapse/analysis/sampling.py`
- Create: `src/kem_timelapse/analysis/analyzer.py`
- Create: `tests/unit/analysis/test_features.py`
- Create: `tests/unit/analysis/test_sampling.py`
- Create: `tests/integration/analysis/test_analyzer_proxy.py`

**Interfaces:**
- Consumes: `ProxyArtifact`, `TrackedRoi`, OpenCV frames, mono PCM samples.
- Produces: `VisualMetrics`, `visual_metrics(previous, current, roi)`, `brush_band_score(samples, sample_rate)`, `sampling_schedule(duration_ms, candidate_ms)`, and `HeuristicAnalyzer.analyze(proxy, audio_envelope, cancel_event) -> list[FeatureWindow]`.

- [ ] **Step 1: Write failing feature-ordering and sampling tests**

```python
# tests/unit/analysis/test_features.py
import cv2
import numpy as np

from kem_timelapse.analysis.features import brush_band_score, visual_metrics


def test_visual_metrics_separate_static_detail_and_broad_change() -> None:
    base = np.zeros((120, 160, 3), dtype=np.uint8)
    static = base.copy()
    detail = base.copy()
    cv2.line(detail, (70, 50), (90, 70), (255, 255, 255), 2)
    broad = base.copy()
    cv2.rectangle(broad, (20, 20), (140, 100), (255, 255, 255), -1)
    static_score = visual_metrics(base, static, None)
    detail_score = visual_metrics(base, detail, None)
    broad_score = visual_metrics(base, broad, None)
    assert static_score.changed_area < detail_score.changed_area < broad_score.changed_area
    assert detail_score.detail > static_score.detail
    assert broad_score.changed_area > 0.35


def test_brush_band_score_prefers_six_khz_over_low_hum() -> None:
    sample_rate = 16_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    brush = np.sin(2 * np.pi * 6_000 * time).astype(np.float32)
    hum = np.sin(2 * np.pi * 100 * time).astype(np.float32)
    assert brush_band_score(brush, sample_rate) > brush_band_score(hum, sample_rate)
```

```python
# tests/unit/analysis/test_sampling.py
from kem_timelapse.analysis.sampling import sampling_schedule


def test_sampling_schedule_is_sparse_except_near_candidates() -> None:
    schedule = sampling_schedule(duration_ms=3_000, candidate_ms=[1_000], sparse_ms=500, dense_ms=100)
    assert 900 in schedule and 1_100 in schedule
    assert 100 not in schedule
    assert 500 in schedule and 2_500 in schedule
    assert schedule == sorted(set(schedule))
```

- [ ] **Step 2: Run the focused tests and verify missing-module failures**

Run: `.venv/bin/pytest tests/unit/analysis/test_features.py tests/unit/analysis/test_sampling.py -q`

Expected: collection fails for missing feature and sampling modules.

- [ ] **Step 3: Implement normalized visual and audio metrics**

`visual_metrics` must crop to the ROI bounding box when present, resize both frames to 320 px width, calculate grayscale absolute difference, threshold at 20/255, derive changed-area ratio, mean normalized difference, Farneback optical-flow magnitude normalized by 8 pixels, and edge-change density from Canny XOR. Clamp every score to 0–1.

`brush_band_score` must apply a Hann window, use `np.fft.rfft`, sum power from 3–8 kHz, divide by power from 80 Hz to Nyquist, and clamp to 0–1. Silence returns 0.

Expose this exact result model:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualMetrics:
    motion: float
    canvas_change: float
    changed_area: float
    detail: float
```

The detail score is `edge_change * (1.0 - changed_area)`, so fine localized strokes outrank full-frame fills while changed area still captures broad painting.

- [ ] **Step 4: Implement sparse/dense sampling and the analyzer loop**

`sampling_schedule` starts with timestamps `range(0, duration_ms, sparse_ms)`. Around every first-pass candidate it adds timestamps from `candidate - 500` through `candidate + 500` at `dense_ms`, clipped to `[0, duration_ms)`. Return a sorted list of unique integers.

`HeuristicAnalyzer.analyze` performs a sparse pass over the proxy, marks candidates where any of motion, canvas change, detail, or audio score exceeds 0.10, then repeats metric extraction on the merged dense schedule. It emits one `FeatureWindow` per adjacent timestamp pair and includes the tracked ROI nearest the window start. Check `cancel_event.is_set()` before every decode seek and raise `InterruptedError("analysis cancelled")` when set.

Use dependency injection for frame reads and the audio envelope in unit tests. The concrete OpenCV reader must seek with `cv2.CAP_PROP_POS_MSEC`, return display-oriented BGR frames, and close `VideoCapture` in `finally`.

- [ ] **Step 5: Add a generated-proxy integration test**

Create a 4-second 1280×720/10 proxy: 1 second static black, 1 second growing white rectangle, 1 second thin moving line, 1 second static final canvas. Supply a deterministic audio envelope with a 0.9 peak during the thin-line second. Assert:

```python
windows = analyzer.analyze(proxy, audio_envelope, threading.Event())
assert windows[0].motion_score < 0.05
assert max(window.changed_area_score for window in windows[10:20]) > 0.20
assert max(window.detail_score for window in windows[20:30]) > windows[0].detail_score
assert max(window.audio_score for window in windows[20:30]) == 0.9
```

- [ ] **Step 6: Run focused, integration, and static checks**

```bash
.venv/bin/pytest tests/unit/analysis/test_features.py tests/unit/analysis/test_sampling.py -q
.venv/bin/pytest tests/integration/analysis/test_analyzer_proxy.py -q
.venv/bin/ruff check src/kem_timelapse/analysis tests/unit/analysis tests/integration/analysis
.venv/bin/mypy src/kem_timelapse/analysis
```

Expected: all tests pass; Ruff and mypy exit 0.

- [ ] **Step 7: Commit two-pass analysis**

```bash
git add src/kem_timelapse/analysis tests/unit/analysis tests/integration/analysis
git commit -m "feat: extract two-pass painting activity features"
```

### Task 7: Hysteresis segmentation and explainable pacing labels

**Files:**
- Create: `src/kem_timelapse/analysis/presets.py`
- Create: `src/kem_timelapse/analysis/segmenter.py`
- Create: `tests/unit/analysis/test_segmenter.py`

**Interfaces:**
- Consumes: ordered `FeatureWindow` values for one clip.
- Produces: immutable `AnalysisPreset` and `segment_windows(windows, preset) -> list[Segment]` with deterministic IDs and reason codes.

- [ ] **Step 1: Write failing tests for inactivity hysteresis, detail retention, and handles**

```python
# tests/unit/analysis/test_segmenter.py
from kem_timelapse.analysis.presets import BOOTSTRAP_PRESET
from kem_timelapse.analysis.segmenter import segment_windows
from kem_timelapse.domain.models import FeatureWindow, SegmentKind


def window(start: int, *, motion: float, area: float, detail: float, audio: float = 0.0) -> FeatureWindow:
    return FeatureWindow(
        source_id="clip-1", start_ms=start, end_ms=start + 500,
        motion_score=motion, canvas_change_score=area, changed_area_score=area,
        detail_score=detail, audio_score=audio,
    )


def test_segmenter_removes_long_static_but_keeps_detail_and_asmr() -> None:
    windows = [window(i * 500, motion=0.01, area=0.01, detail=0.01) for i in range(4)]
    windows += [window(2_000, motion=0.20, area=0.08, detail=0.70)]
    windows += [window(2_500, motion=0.16, area=0.05, detail=0.25, audio=0.80)]
    segments = segment_windows(windows, BOOTSTRAP_PRESET)
    assert segments[0].kind is SegmentKind.INACTIVE
    assert segments[0].keep_default is False
    assert any(segment.kind is SegmentKind.DETAIL for segment in segments)
    assert any(segment.kind is SegmentKind.ASMR_PEAK for segment in segments)
    assert all(segment.start_ms >= 0 for segment in segments)
```

- [ ] **Step 2: Run the test and verify the missing-module failure**

Run: `.venv/bin/pytest tests/unit/analysis/test_segmenter.py -q`

Expected: collection fails because presets/segmenter are absent.

- [ ] **Step 3: Add the versioned bootstrap preset**

```python
# src/kem_timelapse/analysis/presets.py
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisPreset:
    version: str
    active_enter: float
    active_exit: float
    broad_area: float
    detail_score: float
    asmr_score: float
    minimum_inactive_ms: int
    merge_gap_ms: int
    handle_ms: int


BOOTSTRAP_PRESET = AnalysisPreset(
    version="heuristic-v1-bootstrap",
    active_enter=0.12,
    active_exit=0.08,
    broad_area=0.35,
    detail_score=0.18,
    asmr_score=0.55,
    minimum_inactive_ms=1_500,
    merge_gap_ms=500,
    handle_ms=250,
)
```

- [ ] **Step 4: Implement segmentation in four deterministic passes**

Implement these passes in order:

1. Compute activity as `max(motion_score, canvas_change_score, detail_score, audio_score)` and apply enter/exit hysteresis.
2. Group adjacent windows with the same active state; inactive groups shorter than `minimum_inactive_ms` become active.
3. Within active groups classify each window in priority order: `ASMR_PEAK`, `DETAIL`, `BROAD_FILL`, then `PROGRESS`; merge adjacent equal kinds and bridge equal kinds separated by at most `merge_gap_ms`.
4. Add `handle_ms` to kept group boundaries without crossing source start or creating overlaps; create deterministic ID `sha1(source_id:start:end:kind)[:16]` and assign speeds Delete/12/4/2/1 according to the approved mapping.

Every segment receives concrete reason codes such as `activity_below_exit`, `changed_area_ge_0.35`, `detail_ge_0.18`, or `audio_ge_0.55`. Mark the final kept segment `REVEAL_CANDIDATE` when its last second is low-motion and high canvas-change relative to the first window; keep the original classification in `reason_codes`.

- [ ] **Step 5: Add boundary regressions and run all analysis tests**

Add these concrete regressions to `test_segmenter.py`:

```python
import pytest


def inactive_window(end_ms: int) -> FeatureWindow:
    return FeatureWindow(
        source_id="clip-1", start_ms=0, end_ms=end_ms,
        motion_score=0.01, canvas_change_score=0.01, changed_area_score=0.01,
        detail_score=0.01, audio_score=0.01,
    )


@pytest.mark.parametrize(("duration_ms", "deleted"), [(1_499, False), (1_500, True)])
def test_inactivity_threshold_is_inclusive(duration_ms: int, deleted: bool) -> None:
    result = segment_windows([inactive_window(duration_ms)], BOOTSTRAP_PRESET)
    assert (result[0].kind is SegmentKind.INACTIVE and not result[0].keep_default) is deleted


def test_output_is_deterministic_non_overlapping_and_clamped() -> None:
    windows = [inactive_window(1_500), window(1_500, motion=0.3, area=0.4, detail=0.1)]
    first = segment_windows(windows, BOOTSTRAP_PRESET)
    second = segment_windows(windows, BOOTSTRAP_PRESET)
    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].start_ms == 0
    assert all(left.end_ms <= right.start_ms for left, right in zip(first, first[1:]))
```

```python
def ranged_window(start_ms: int, end_ms: int, *, detail: float) -> FeatureWindow:
    return FeatureWindow(
        source_id="clip-1", start_ms=start_ms, end_ms=end_ms,
        motion_score=0.20 if detail else 0.01,
        canvas_change_score=0.05, changed_area_score=0.05,
        detail_score=detail, audio_score=0.0,
    )


@pytest.mark.parametrize(("gap_ms", "detail_segment_count"), [(500, 1), (501, 2)])
def test_equal_kinds_bridge_only_through_configured_gap(gap_ms: int, detail_segment_count: int) -> None:
    windows = [
        ranged_window(0, 1_000, detail=0.7),
        ranged_window(1_000, 1_000 + gap_ms, detail=0.0),
        ranged_window(1_000 + gap_ms, 2_000 + gap_ms, detail=0.7),
    ]
    result = segment_windows(windows, BOOTSTRAP_PRESET)
    assert sum(item.kind is SegmentKind.DETAIL for item in result) == detail_segment_count
```

Run:

```bash
.venv/bin/pytest tests/unit/analysis tests/integration/analysis -q
.venv/bin/ruff check src/kem_timelapse/analysis tests/unit/analysis
.venv/bin/mypy src/kem_timelapse/analysis
```

Expected: all analysis tests pass; static checks exit 0.

- [ ] **Step 6: Commit explainable segmentation**

```bash
git add src/kem_timelapse/analysis/presets.py src/kem_timelapse/analysis/segmenter.py tests/unit/analysis/test_segmenter.py
git commit -m "feat: segment activity with explainable pacing rules"
```

### Task 8: Three duration-budgeted platform composers

**Files:**
- Create: `src/kem_timelapse/compose/presets.py`
- Create: `src/kem_timelapse/compose/composer.py`
- Create: `tests/unit/compose/test_composer.py`

**Interfaces:**
- Consumes: canonical `Segment` pool and `Variant`.
- Produces: `ComposerPreset`, `timeline_duration_ms(timeline)`, `compose_timeline(segments, preset) -> Timeline`, and presets `TIKTOK`, `REELS`, `SHORTS`.

- [ ] **Step 1: Write failing tests proving three independent budgets and reveal structure**

```python
# tests/unit/compose/test_composer.py
from kem_timelapse.compose.composer import compose_timeline, timeline_duration_ms
from kem_timelapse.compose.presets import REELS, SHORTS, TIKTOK
from kem_timelapse.domain.models import Segment, SegmentKind, Variant


def segment(index: int, kind: SegmentKind, duration_ms: int, score: float) -> Segment:
    start = index * 20_000
    return Segment(
        id=f"s-{index}", source_id="clip-1", start_ms=start, end_ms=start + duration_ms,
        kind=kind, activity_score=score, detail_score=score, audio_score=score,
        roi_confidence=0.9, recommended_speed=2, keep_default=True,
        reason_codes=[kind.value],
    )


def pool() -> list[Segment]:
    kinds = [
        SegmentKind.REVEAL_CANDIDATE, SegmentKind.BROAD_FILL, SegmentKind.PROGRESS,
        SegmentKind.DETAIL, SegmentKind.ASMR_PEAK, SegmentKind.DETAIL,
        SegmentKind.PROGRESS, SegmentKind.REVEAL_CANDIDATE,
    ]
    return [segment(index, kind, 20_000, 0.5 + index * 0.05) for index, kind in enumerate(kinds)]


def test_all_composers_meet_duration_and_structure_contracts() -> None:
    contracts = [(TIKTOK, Variant.TIKTOK_FAST), (REELS, Variant.REELS_AESTHETIC), (SHORTS, Variant.SHORTS_ASMR)]
    timelines = [compose_timeline(pool(), preset) for preset, _ in contracts]
    for timeline, (preset, variant) in zip(timelines, contracts):
        assert timeline.variant is variant
        assert preset.min_ms <= timeline_duration_ms(timeline) <= preset.max_ms
        assert timeline.items[0].segment_id in {"s-0", "s-7"}
        assert timeline.items[-1].segment_id in {"s-0", "s-7"}
    assert timelines[0].model_dump() != timelines[1].model_dump()
    assert timelines[1].model_dump() != timelines[2].model_dump()
```

- [ ] **Step 2: Run the test and verify it fails for missing composer code**

Run: `.venv/bin/pytest tests/unit/compose/test_composer.py -q`

Expected: collection fails because `kem_timelapse.compose` is missing.

- [ ] **Step 3: Define immutable platform presets**

```python
# src/kem_timelapse/compose/presets.py
from dataclasses import dataclass
from typing import Literal

from kem_timelapse.domain.models import SegmentKind, Speed, Variant


@dataclass(frozen=True)
class ComposerPreset:
    variant: Variant
    min_ms: int
    target_ms: int
    max_ms: int
    hook_ms: int
    reveal_ms: int
    audio_mode: Literal["asmr_music", "asmr", "music", "silent"]
    speed_by_kind: dict[SegmentKind, Speed]
    score_weights: dict[SegmentKind, float]


TIKTOK = ComposerPreset(
    Variant.TIKTOK_FAST, 25_000, 30_000, 35_000, 1_250, 2_500, "asmr_music",
    {SegmentKind.BROAD_FILL: 12, SegmentKind.PROGRESS: 12, SegmentKind.DETAIL: 4,
     SegmentKind.ASMR_PEAK: 2, SegmentKind.REVEAL_CANDIDATE: 1},
    {SegmentKind.BROAD_FILL: 1.0, SegmentKind.PROGRESS: 1.2, SegmentKind.DETAIL: 1.1,
     SegmentKind.ASMR_PEAK: 0.8, SegmentKind.REVEAL_CANDIDATE: 2.0},
)
REELS = ComposerPreset(
    Variant.REELS_AESTHETIC, 35_000, 42_000, 50_000, 1_500, 4_000, "asmr_music",
    {SegmentKind.BROAD_FILL: 12, SegmentKind.PROGRESS: 4, SegmentKind.DETAIL: 2,
     SegmentKind.ASMR_PEAK: 2, SegmentKind.REVEAL_CANDIDATE: 1},
    {SegmentKind.BROAD_FILL: 0.8, SegmentKind.PROGRESS: 1.1, SegmentKind.DETAIL: 1.4,
     SegmentKind.ASMR_PEAK: 1.1, SegmentKind.REVEAL_CANDIDATE: 2.0},
)
SHORTS = ComposerPreset(
    Variant.SHORTS_ASMR, 55_000, 70_000, 90_000, 1_500, 5_000, "asmr",
    {SegmentKind.BROAD_FILL: 4, SegmentKind.PROGRESS: 4, SegmentKind.DETAIL: 2,
     SegmentKind.ASMR_PEAK: 1, SegmentKind.REVEAL_CANDIDATE: 1},
    {SegmentKind.BROAD_FILL: 0.4, SegmentKind.PROGRESS: 0.8, SegmentKind.DETAIL: 1.6,
     SegmentKind.ASMR_PEAK: 2.0, SegmentKind.REVEAL_CANDIDATE: 1.8},
)
```

- [ ] **Step 4: Implement deterministic constrained composition**

`compose_timeline` must:

1. Remove `keep_default=False` and `INACTIVE` segments.
2. Pick the highest-scoring reveal candidate, or the latest kept segment if none is labeled.
3. Duplicate a trimmed reveal reference as the first hook item and keep a separate reveal item last. Give every item a unique deterministic ID of the form `{variant}-{role}-{segment_id}-{ordinal}` even when hook and reveal share a segment.
4. Score body candidates by the preset weight multiplied by the maximum of activity/detail/audio; preserve chronological order after selection.
5. Add candidates until `target_ms`; trim the last candidate if needed; never exceed `max_ms`.
6. If below `min_ms`, add the next best unused candidates or reduce eligible 4× speeds to 2× and 2× to 1× until the minimum is reached.
7. Validate that hook and reveal remain, all speeds are canonical, and total duration falls inside the contract; otherwise raise `PipelineError(ErrorCode.TIMELINE_INVALID, "duration outside preset", context={"variant": preset.variant.value, "duration_ms": duration_ms})`.

Compute timeline duration as the rounded sum of `(trim_out_ms - trim_in_ms) / speed` for kept items. `trim_in_ms` and `trim_out_ms` are absolute timestamps in the referenced source clip, never offsets relative to the segment. Set revision 0 and the preset audio mode. Treat the input segment list as canonical source order; sorting ties use original list index, source timestamp, then segment ID so repeated runs are byte-stable.

- [ ] **Step 5: Add scarcity and determinism regressions**

Add these regressions to `test_composer.py`:

```python
import pytest

from kem_timelapse.domain.errors import ErrorCode, PipelineError


def test_composers_are_deterministic_and_platform_specific() -> None:
    source = pool()
    tiktok_a = compose_timeline(source, TIKTOK)
    tiktok_b = compose_timeline(source, TIKTOK)
    shorts = compose_timeline(source, SHORTS)
    assert tiktok_a.model_dump(mode="json") == tiktok_b.model_dump(mode="json")
    assert sum(item.speed == 12 for item in tiktok_a.items) > sum(item.speed == 12 for item in shorts.items)
    asmr_id = max(
        (item for item in source if item.kind is SegmentKind.ASMR_PEAK),
        key=lambda item: item.audio_score,
    ).id
    assert any(item.segment_id == asmr_id for item in shorts.items)


def test_inactivity_is_never_composed() -> None:
    source = pool() + [segment(9, SegmentKind.INACTIVE, 60_000, 1.0).model_copy(update={"keep_default": False})]
    timeline = compose_timeline(source, SHORTS)
    assert "s-9" not in {item.segment_id for item in timeline.items}


def test_missing_reveal_falls_back_to_latest_kept_segment() -> None:
    source = [segment(index, SegmentKind.DETAIL, 40_000, 0.8) for index in range(4)]
    timeline = compose_timeline(source, SHORTS)
    assert timeline.items[0].segment_id == "s-3"
    assert timeline.items[-1].segment_id == "s-3"


def test_insufficient_material_has_stable_blocking_error() -> None:
    with pytest.raises(PipelineError) as caught:
        compose_timeline([segment(0, SegmentKind.DETAIL, 1_000, 0.8)], SHORTS)
    assert caught.value.code is ErrorCode.TIMELINE_INVALID
    assert caught.value.context["variant"] == Variant.SHORTS_ASMR.value
```

Run:

```bash
.venv/bin/pytest tests/unit/compose -q
.venv/bin/ruff check src/kem_timelapse/compose tests/unit/compose
.venv/bin/mypy src/kem_timelapse/compose
```

Expected: all composer tests pass; static checks exit 0.

- [ ] **Step 6: Commit Content Pack composition**

```bash
git add src/kem_timelapse/compose tests/unit/compose
git commit -m "feat: compose three platform-specific timelines"
```

### Task 9: Non-destructive timeline edits, Undo/Redo, and Copy to all

**Files:**
- Create: `src/kem_timelapse/editing/commands.py`
- Create: `src/kem_timelapse/editing/session.py`
- Create: `tests/unit/editing/test_session.py`

**Interfaces:**
- Consumes: `Timeline`, `TimelineItem`, `CropOverride`, `Variant`, `ProjectRepository.save_timeline`.
- Produces: edit commands `SetKeep`, `SetSpeed`, `SetCrop`, `SetWatermark`; `EditingSession.apply`, `undo`, `redo`, `snapshot`; and `copy_shared_edits(source, targets)`.

- [ ] **Step 1: Write failing edit-isolation and history tests**

```python
# tests/unit/editing/test_session.py
from kem_timelapse.domain.models import Timeline, TimelineItem, Variant
from kem_timelapse.editing.commands import SetKeep, SetSpeed
from kem_timelapse.editing.session import EditingSession, copy_shared_edits


def timeline(variant: Variant) -> Timeline:
    return Timeline(
        variant=variant, revision=0, audio_mode="asmr_music",
        items=[TimelineItem(id="body-shared", role="body", segment_id="shared", trim_in_ms=0, trim_out_ms=4_000, speed=4)],
    )


def test_apply_undo_redo_are_immutable() -> None:
    original = timeline(Variant.TIKTOK_FAST)
    session = EditingSession(original)
    changed = session.apply(SetSpeed(item_id="body-shared", speed=2))
    assert original.items[0].speed == 4
    assert changed.items[0].speed == 2 and changed.revision == 1
    assert session.undo().items[0].speed == 4
    assert session.redo().items[0].speed == 2


def test_copy_to_all_only_updates_segments_present_in_targets() -> None:
    source = EditingSession(timeline(Variant.TIKTOK_FAST)).apply(SetKeep(item_id="body-shared", keep=False))
    target = timeline(Variant.REELS_AESTHETIC)
    copied = copy_shared_edits(source, [target])[0]
    assert copied.variant is Variant.REELS_AESTHETIC
    assert copied.items[0].keep is False
    assert copied.revision == 1
```

- [ ] **Step 2: Run tests and verify missing-module failures**

Run: `.venv/bin/pytest tests/unit/editing/test_session.py -q`

Expected: collection fails because `kem_timelapse.editing` is absent.

- [ ] **Step 3: Implement typed edit commands and immutable application**

Define commands as frozen dataclasses:

```python
@dataclass(frozen=True)
class SetKeep:
    item_id: str
    keep: bool


@dataclass(frozen=True)
class SetSpeed:
    item_id: str
    speed: Speed


@dataclass(frozen=True)
class SetCrop:
    item_id: str
    crop: CropOverride | None


@dataclass(frozen=True)
class SetWatermark:
    text: str
    opacity: float
```

`EditingSession.apply` uses `model_copy(deep=True)`, changes exactly one matching timeline item by `item_id` or the timeline watermark, increments revision once, validates through `Timeline.model_validate`, appends the previous snapshot to `_undo`, and clears `_redo`. Missing item IDs raise `PipelineError(ErrorCode.TIMELINE_INVALID, "item is not present in timeline", context={"item_id": command.item_id})`. History is capped at 100 snapshots.

- [ ] **Step 4: Implement Undo/Redo and shared-edit copying**

`undo` and `redo` move immutable snapshots between stacks and return the active timeline. Empty-stack calls return the current timeline unchanged. `copy_shared_edits` copies `keep` and `crop_override` by `(role, segment_id)`, plus watermark text/opacity, but does not copy item order, trim, speed, variant, or audio mode. Increment each changed target revision exactly once.

- [ ] **Step 5: Persist every accepted revision and run checks**

Add `PersistingEditingSession(EditingSession)` or an injected `on_change: Callable[[Timeline], None]` callback. Test that apply/undo/redo each call `ProjectRepository.save_timeline` with the active revision, while a rejected command writes nothing.

Run:

```bash
.venv/bin/pytest tests/unit/editing tests/unit/storage -q
.venv/bin/ruff check src/kem_timelapse/editing tests/unit/editing
.venv/bin/mypy src/kem_timelapse/editing
```

Expected: all editing/storage tests pass; static checks exit 0.

- [ ] **Step 6: Commit preview editing semantics**

```bash
git add src/kem_timelapse/editing tests/unit/editing
git commit -m "feat: add non-destructive timeline editing history"
```

### Task 10: Selected-range ASMR stems, denoise fallback, and music ducking

**Files:**
- Create: `src/kem_timelapse/audio/models.py`
- Create: `src/kem_timelapse/audio/ranges.py`
- Create: `src/kem_timelapse/audio/backends.py`
- Create: `src/kem_timelapse/audio/pipeline.py`
- Create: `tests/unit/audio/test_ranges.py`
- Create: `tests/unit/audio/test_pipeline.py`
- Create: `tests/integration/audio/test_ffmpeg_mix.py`

**Interfaces:**
- Consumes: all three `Timeline` values, canonical `Segment` map, source paths, project `cache/audio`, optional local music path, `CommandRunner`.
- Produces: `SourceRange`, `DenoiseResult`, `AudioStem`, `AudioMixPlan`, `merge_selected_ranges`, `DeepFilterBackend`, `FfmpegDenoiseBackend`, and `AudioPipeline.prepare_variant(variant: Variant, timelines: Sequence[Timeline], segments: Mapping[str, Segment], sources: Mapping[str, SourceClip], cache_dir: Path, music_path: Path | None, rights_confirmed: bool) -> AudioMixPlan`.

- [ ] **Step 1: Write failing range-union and fallback tests**

```python
# tests/unit/audio/test_ranges.py
from kem_timelapse.audio.models import SourceRange
from kem_timelapse.audio.ranges import merge_selected_ranges


def test_merge_selected_ranges_unions_overlap_and_small_gaps_per_source() -> None:
    ranges = [
        SourceRange(source_id="a", start_ms=0, end_ms=1_000),
        SourceRange(source_id="a", start_ms=900, end_ms=2_000),
        SourceRange(source_id="a", start_ms=2_100, end_ms=3_000),
        SourceRange(source_id="b", start_ms=0, end_ms=500),
    ]
    assert merge_selected_ranges(ranges, join_gap_ms=100) == [
        SourceRange(source_id="a", start_ms=0, end_ms=3_000),
        SourceRange(source_id="b", start_ms=0, end_ms=500),
    ]
```

```python
# tests/unit/audio/test_pipeline.py
from pathlib import Path

from kem_timelapse.audio.pipeline import AudioPipeline
from kem_timelapse.domain.errors import WarningCode


class FailingDenoiser:
    def process(self, input_wav: Path, output_wav: Path) -> None:
        raise RuntimeError("model unavailable")


class RecordingFallback:
    def __init__(self) -> None:
        self.called = False

    def process(self, input_wav: Path, output_wav: Path) -> None:
        self.called = True
        output_wav.write_bytes(input_wav.read_bytes())


def test_denoise_failure_uses_ffmpeg_fallback_and_warning(tmp_path: Path) -> None:
    source = tmp_path / "selected.wav"
    source.write_bytes(b"wav")
    fallback = RecordingFallback()
    pipeline = AudioPipeline(primary=FailingDenoiser(), fallback=fallback)
    result = pipeline.denoise(source, tmp_path / "clean.wav")
    assert fallback.called is True
    assert result.warning is WarningCode.AUDIO_DENOISE_DEGRADED
    assert result.path.read_bytes() == b"wav"
```

- [ ] **Step 2: Run focused tests and verify missing-module failures**

Run: `.venv/bin/pytest tests/unit/audio -q`

Expected: collection fails because `kem_timelapse.audio` is absent.

- [ ] **Step 3: Implement selected-range models and interval union**

```python
# src/kem_timelapse/audio/models.py
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Variant


class SourceRange(BaseModel):
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "SourceRange":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class AudioStem(BaseModel):
    source_range: SourceRange
    path: Path
    cache_key: str
    warning: WarningCode | None = None


class DenoiseResult(BaseModel):
    path: Path
    warning: WarningCode | None = None


class AudioMixPlan(BaseModel):
    variant: Variant
    mode: Literal["asmr_music", "asmr", "music", "silent"]
    stem_paths: list[Path]
    music_path: Path | None
    filter_graph: str
    mix_path: Path
    warning_codes: list[WarningCode]
```

`merge_selected_ranges` sorts by `(source_id, start_ms, end_ms)`, merges overlap and gaps less than or equal to `join_gap_ms`, and never merges across sources. `ranges_from_timelines` resolves kept `TimelineItem.segment_id` values through a `Mapping[str, Segment]`, treats item trims as absolute source timestamps, validates them inside the segment range, de-duplicates ranges used by multiple variants, then calls the union function.

- [ ] **Step 4: Implement DeepFilterNet and FFmpeg denoise adapters**

Use a protocol with `process(input_wav: Path, output_wav: Path) -> None`. `DeepFilterBackend` lazily imports `df.enhance`, calls `init_df`, `load_audio`, `enhance`, and `save_audio`; initialization is cached for the app process. Import/model errors are allowed to escape to `AudioPipeline`, which invokes `FfmpegDenoiseBackend`.

`FfmpegDenoiseBackend` runs this argument list and rejects a missing/empty output:

```python
[
    "ffmpeg", "-y", "-v", "error", "-i", str(input_wav),
    "-af", "highpass=f=80,afftdn=nf=-25,equalizer=f=3000:t=q:w=1:g=2,"
           "equalizer=f=8000:t=q:w=1:g=1,acompressor=threshold=-18dB:ratio=3:attack=10:release=120,"
           "alimiter=limit=0.891",
    str(output_wav),
]
```

`AudioPipeline.denoise(input_wav: Path, output_wav: Path) -> DenoiseResult` writes to a `.partial.wav` sibling, atomic-renames success, and returns warning `AudioDenoiseDegraded` only when fallback ran.

- [ ] **Step 5: Implement stem caching and per-platform mix plans**

For each merged range, extract 48 kHz mono PCM WAV from the original source with `-ss` before `-i`, exact `-t`, `-vn`, `-ac 1`, `-ar 48000`, and `pcm_s24le`. Cache key includes source fingerprint, absolute range, audio preset version `audio-v1`, and backend name. Never run denoise twice for a valid non-empty cache artifact.

Build exact mix policy:

- TikTok: music gain −18 dB; sidechain compression equivalent to about 6 dB duck, attack 20 ms, release 250 ms.
- Reels: music gain −21 dB; duck about 4 dB, attack 40 ms, release 400 ms.
- Shorts: ASMR only by default; when music is enabled, gain −28 dB and duck about 3 dB.
- Final filter always ends in `loudnorm=I=-14:TP=-1:LRA=7` and `alimiter=limit=0.891`.
- `silent` uses `anullsrc=r=48000:cl=stereo`; `music` omits the ASMR sidechain; missing source audio adds `NoSourceAudio`.

Render the resulting mix to `cache/audio/<variant>-<cache-key>.wav` as stereo 48 kHz `pcm_s24le`, first through a `.partial.wav` file and then atomic rename. Store that final path in `AudioMixPlan.mix_path`; the video renderer consumes this file and never rebuilds audio filters.

Reject a music path unless it exists and the caller passes `rights_confirmed=True`. This is local validation only; do not claim license verification.

- [ ] **Step 6: Add a real FFmpeg golden-audio integration test**

Generate a 10-second WAV containing low 100 Hz hum plus six 200 ms bursts at 6 kHz, and a separate 10-second pink-noise music WAV. Run the fallback ASMR chain and mix plan. Measure with FFmpeg `ebur128=peak=true`; assert integrated loudness is −14 LUFS ±1 LU, true peak is at most −1 dBTP +0.2 dB tolerance, no clipped samples, and output duration differs by less than 50 ms. Mark the test `media`.

- [ ] **Step 7: Run audio tests and static checks**

```bash
.venv/bin/pytest tests/unit/audio -q
.venv/bin/pytest tests/integration/audio/test_ffmpeg_mix.py -m media -q
.venv/bin/ruff check src/kem_timelapse/audio tests/unit/audio tests/integration/audio
.venv/bin/mypy src/kem_timelapse/audio
```

Expected: unit tests pass; media test passes or intentionally skips only when FFmpeg is unavailable; static checks exit 0.

- [ ] **Step 8: Commit selected-range ASMR processing**

```bash
git add src/kem_timelapse/audio tests/unit/audio tests/integration/audio
git commit -m "feat: process selected ASMR ranges with denoise fallback"
```

### Task 11: Smooth 9:16 crop keyframes and safe watermark placement

**Files:**
- Create: `src/kem_timelapse/framing/models.py`
- Create: `src/kem_timelapse/framing/crop.py`
- Create: `src/kem_timelapse/framing/watermark.py`
- Create: `tests/unit/framing/test_crop.py`
- Create: `tests/unit/framing/test_watermark.py`

**Interfaces:**
- Consumes: timestamped `TrackedRoi` samples, source display dimensions, optional `CropOverride`, saliency grid, watermark text/opacity.
- Produces: `CropKeyframe`, `FramingPlan`, `plan_vertical_crop(samples: Sequence[TrackedRoi], source_width: int, source_height: int, override: CropOverride | None = None) -> FramingPlan`, `WatermarkPlacement`, and `choose_watermark_placement(saliency: NDArray[np.float32], canvas_box: tuple[float, float, float, float], text: str, opacity: float) -> WatermarkPlacement`.

- [ ] **Step 1: Write failing crop-fallback and watermark-safe-zone tests**

```python
# tests/unit/framing/test_crop.py
from kem_timelapse.analysis.roi import TrackedRoi
from kem_timelapse.domain.models import Point, Roi
from kem_timelapse.framing.crop import plan_vertical_crop


def roi(center_x: float, confidence: float = 0.9, manual: bool = False) -> Roi:
    return Roi(
        points=(
            Point(x=center_x - 0.2, y=0.2), Point(x=center_x + 0.2, y=0.2),
            Point(x=center_x + 0.2, y=0.8), Point(x=center_x - 0.2, y=0.8),
        ),
        confidence=confidence,
        manual=manual,
    )


def test_crop_smooths_motion_and_requires_manual_low_confidence() -> None:
    samples = [
        TrackedRoi(timestamp_ms=0, roi=roi(0.4), fallback="none", warning=False),
        TrackedRoi(timestamp_ms=500, roi=roi(0.8), fallback="none", warning=False),
        TrackedRoi(timestamp_ms=1_000, roi=roi(0.8, confidence=0.4), fallback="none", warning=False),
    ]
    plan = plan_vertical_crop(samples, source_width=3840, source_height=2160)
    assert plan.keyframes[1].center_x < 0.8
    assert plan.requires_manual_roi is True
    assert plan.crop_width == 1214 and plan.crop_height == 2160
```

```python
# tests/unit/framing/test_watermark.py
import numpy as np

from kem_timelapse.framing.watermark import choose_watermark_placement


def test_watermark_chooses_low_saliency_corner_outside_canvas() -> None:
    saliency = np.zeros((10, 10), dtype=np.float32)
    saliency[0:3, 0:3] = 1.0
    placement = choose_watermark_placement(
        saliency, canvas_box=(0.2, 0.1, 0.9, 0.65), text="@kem12032024", opacity=0.30,
    )
    assert placement.corner == "bottom-left"
    assert placement.opacity == 0.30
    assert placement.warning is None
```

- [ ] **Step 2: Run tests and verify missing-module failures**

Run: `.venv/bin/pytest tests/unit/framing -q`

Expected: collection fails because `kem_timelapse.framing` is absent.

- [ ] **Step 3: Implement crop models and vertical crop geometry**

```python
# src/kem_timelapse/framing/models.py
from typing import Literal

from pydantic import BaseModel, Field

from kem_timelapse.domain.errors import WarningCode


class CropKeyframe(BaseModel):
    timestamp_ms: int = Field(ge=0)
    center_x: float = Field(ge=0.0, le=1.0)
    center_y: float = Field(ge=0.0, le=1.0)
    scale: float = Field(gt=0.0, le=4.0)


class FramingPlan(BaseModel):
    crop_width: int
    crop_height: int
    keyframes: list[CropKeyframe]
    requires_manual_roi: bool
    warning_codes: list[WarningCode]


class WatermarkPlacement(BaseModel):
    corner: Literal["top-left", "bottom-left", "top-right", "bottom-right"]
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    text: str
    opacity: float = Field(ge=0.0, le=1.0)
    warning: WarningCode | None = None
```

For landscape source, use full source height and the largest even crop width not exceeding `floor(height * 9 / 16)`; 3840×2160 yields **1214×2160** after even rounding, then scale to 1080×1920. For a portrait source, use full width and the largest even crop height at 16:9.

Center each ROI by averaging four points. Clamp the center so the crop never leaves source bounds. Exponential-smooth with alpha 0.20; also clamp movement to 5% normalized width/height per 500 ms. Use center `(0.5, 0.5)` for `fallback="center"`. Any non-manual ROI confidence below 0.60 sets `requires_manual_roi=True` and warning `LowRoiConfidence`.

- [ ] **Step 4: Implement safe-zone-aware watermark selection**

Reserve top 8%, bottom 18%, and right 15% of the 9:16 frame for platform UI. Evaluate candidates in deterministic order bottom-left, top-left, bottom-right, top-right. Reject a candidate whose text box overlaps the canvas bounding box or forbidden safe zones. Score the remainder by mean saliency; choose the lowest. If every candidate is rejected, choose bottom-left with warning `WatermarkPlacementFallback`. The user override bypasses scoring but still clamps x/y into frame bounds.

- [ ] **Step 5: Add crop velocity, tracker-loss, and all-corners-blocked regressions**

Add these regressions:

```python
# tests/unit/framing/test_crop.py
def test_crop_velocity_is_clamped_and_center_fallback_is_stable() -> None:
    samples = [
        TrackedRoi(timestamp_ms=0, roi=roi(0.2), fallback="none", warning=False),
        TrackedRoi(timestamp_ms=500, roi=roi(0.8), fallback="none", warning=False),
        TrackedRoi(timestamp_ms=1_500, roi=None, fallback="center", warning=True),
    ]
    plan = plan_vertical_crop(samples, source_width=3840, source_height=2160)
    assert plan.keyframes[1].center_x - plan.keyframes[0].center_x <= 0.05
    assert plan.keyframes[-1].center_x == 0.5
    assert plan.crop_width % 2 == 0 and plan.crop_height % 2 == 0


def test_manual_roi_clears_low_confidence_block() -> None:
    sample = TrackedRoi(timestamp_ms=0, roi=roi(0.5, confidence=0.4, manual=True), fallback="none", warning=False)
    assert plan_vertical_crop([sample], 3840, 2160).requires_manual_roi is False
```

```python
# tests/unit/framing/test_watermark.py
from kem_timelapse.domain.errors import WarningCode


def test_all_blocked_corners_use_deterministic_fallback() -> None:
    saliency = np.ones((10, 10), dtype=np.float32)
    result = choose_watermark_placement(
        saliency, canvas_box=(0.0, 0.0, 1.0, 1.0), text="@kem12032024", opacity=0.30,
    )
    assert result.corner == "bottom-left"
    assert result.warning is WarningCode.WATERMARK_PLACEMENT_FALLBACK
```

Run:

```bash
.venv/bin/pytest tests/unit/framing tests/unit/analysis/test_roi.py -q
.venv/bin/ruff check src/kem_timelapse/framing tests/unit/framing
.venv/bin/mypy src/kem_timelapse/framing
```

Expected: all framing/ROI tests pass; static checks exit 0.

- [ ] **Step 6: Commit framing and watermark plans**

```bash
git add src/kem_timelapse/framing tests/unit/framing
git commit -m "feat: plan smooth vertical framing and watermark placement"
```

### Task 12: FFmpeg render plans, atomic output, validation, and manifest

**Files:**
- Create: `src/kem_timelapse/render/models.py`
- Create: `src/kem_timelapse/render/filtergraph.py`
- Create: `src/kem_timelapse/render/renderer.py`
- Create: `src/kem_timelapse/render/validator.py`
- Create: `src/kem_timelapse/render/manifest.py`
- Create: `tests/unit/render/test_filtergraph.py`
- Create: `tests/unit/render/test_validator.py`
- Create: `tests/unit/render/test_renderer.py`
- Create: `tests/integration/render/test_vertical_output.py`

**Interfaces:**
- Consumes: source map, `Timeline`, `Segment` map, `AudioMixPlan`, `FramingPlan`, `WatermarkPlacement`, `CommandRunner`.
- Produces: `RenderPlan`, `OutputProbe`, `build_render_plan(timeline: Timeline, segments: Mapping[str, Segment], sources: Mapping[str, SourceClip], audio: AudioMixPlan, framing: FramingPlan, watermark: WatermarkPlacement, output_dir: Path, painting_slug: str) -> RenderPlan`, `Renderer.render(plan: RenderPlan, cancel_event: threading.Event, overwrite: bool = False) -> OutputProbe`, `OutputValidator.validate(path: Path) -> OutputProbe`, and `write_manifest(project_root: Path, entry: ManifestEntry) -> None`.

- [ ] **Step 1: Write failing filtergraph and output-contract tests**

```python
# tests/unit/render/test_filtergraph.py
from pathlib import Path

from kem_timelapse.domain.models import Segment, SegmentKind, Timeline, TimelineItem, Variant
from kem_timelapse.render.filtergraph import build_video_filtergraph


def test_filtergraph_trims_speeds_crops_concats_and_watermarks() -> None:
    segments = {
        "s1": Segment(
            id="s1", source_id="clip-1", start_ms=1_000, end_ms=5_000,
            kind=SegmentKind.DETAIL, activity_score=0.8, detail_score=0.9,
            audio_score=0.7, roi_confidence=0.9, recommended_speed=2,
            keep_default=True, reason_codes=["detail"],
        )
    }
    timeline = Timeline(
        variant=Variant.SHORTS_ASMR, revision=0, audio_mode="asmr",
        items=[TimelineItem(id="shorts-body-s1-0", role="body", segment_id="s1", trim_in_ms=1_000, trim_out_ms=5_000, speed=2)],
    )
    graph = build_video_filtergraph(
        timeline,
        segments,
        input_indexes={"clip-1": 0},
        crop_expressions={"s1": ("1214", "2160", "1313", "0")},
    )
    assert "trim=start=1:end=5" in graph
    assert "setpts=(PTS-STARTPTS)/2" in graph
    assert "scale=1080:1920" in graph
    assert "drawtext=text='@kem12032024':fontcolor=white@0.3" in graph
```

```python
# tests/unit/render/test_validator.py
import json
from pathlib import Path

from kem_timelapse.media.process import CompletedCommand
from kem_timelapse.render.validator import OutputValidator


class FakeProbeRunner:
    def run(self, args: list[str], cancel_event: object | None = None) -> CompletedCommand:
        payload = {
            "format": {"format_name": "mov,mp4", "start_time": "0.000000", "duration": "30.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920,
                 "pix_fmt": "yuv420p", "avg_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        return CompletedCommand(0, json.dumps(payload), "")


def test_validator_accepts_exact_vertical_contract(tmp_path: Path) -> None:
    output = tmp_path / "video.mp4"
    output.write_bytes(b"mp4")
    probe = OutputValidator(FakeProbeRunner()).validate(output)
    assert probe.width == 1080 and probe.height == 1920
    assert probe.fps == 30.0 and probe.has_aac is True
```

- [ ] **Step 2: Run tests and verify missing-module failures**

Run: `.venv/bin/pytest tests/unit/render -q`

Expected: collection fails because `kem_timelapse.render` is absent.

- [ ] **Step 3: Implement deterministic filtergraph generation**

Define the render contract models before the builder:

```python
# src/kem_timelapse/render/models.py
from pathlib import Path

from pydantic import BaseModel, Field

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Variant


class RenderPlan(BaseModel):
    variant: Variant
    source_paths: list[Path]
    audio_mix_path: Path
    video_filter_graph: str
    final_path: Path
    temporary_path: Path
    expected_duration_ms: int = Field(gt=0)
    warning_codes: list[WarningCode]


class OutputProbe(BaseModel):
    path: Path
    video_codec: str
    width: int
    height: int
    pixel_format: str
    fps: float
    audio_codec: str
    has_aac: bool
    start_time_ms: int
    duration_ms: int = Field(gt=0)


class ManifestEntry(BaseModel):
    variant: Variant
    filename: str
    sha256: str
    timeline_revision: int
    elapsed_seconds: float = Field(ge=0.0)
    probe: OutputProbe
    warning_codes: list[WarningCode]
```

Add `safe_painting_slug(value: str) -> str` using `unicodedata.normalize("NFKD", value)`, removal of combining marks, lowercase ASCII alphanumerics, collapsed hyphens, and fallback `painting`. `build_render_plan` must produce `<slug>_<variant.value>.mp4` and its sibling `.partial.mp4`.

```python
# append to tests/unit/render/test_renderer.py
from kem_timelapse.domain.models import Variant
from kem_timelapse.render.renderer import output_filename, safe_painting_slug


def test_output_names_are_ascii_and_platform_specific() -> None:
    assert safe_painting_slug("Tranh Biển 07") == "tranh-bien-07"
    assert [output_filename("Tranh Biển 07", variant) for variant in Variant] == [
        "tranh-bien-07_tiktok-fast.mp4",
        "tranh-bien-07_reels-aesthetic.mp4",
        "tranh-bien-07_shorts-asmr.mp4",
    ]
```

For each kept item, resolve the segment and source input index. Convert absolute millisecond trim to seconds, then emit:

```text
[N:v]trim=start=S:end=E,setpts=(PTS-STARTPTS)/SPEED,
crop=W:H:X:Y,scale=1080:1920:flags=lanczos,setsar=1,fps=30,format=yuv420p[vI]
```

Join item labels with `concat=n=COUNT:v=1:a=0[joined]`. Apply watermark last with `drawtext`, escape backslash, colon, apostrophe, percent, and brackets, and use the chosen corner x/y expression. The final label is `[vout]`. Reject empty timelines, missing segments, invalid source indexes, low-confidence unconfirmed ROI, and unsafe watermark text via `TimelineInvalid`.

The command must be a `list[str]`:

```python
args = ["ffmpeg", "-y", "-v", "error"]
for source in ordered_sources:
    args.extend(["-i", str(source.path)])
args.extend([
    "-i", str(audio_mix_path),
    "-filter_complex", video_filtergraph,
    "-map", "[vout]", "-map", f"{len(ordered_sources)}:a:0",
    "-c:v", "h264_videotoolbox", "-pix_fmt", "yuv420p", "-r", "30",
    "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart",
    str(temporary_output),
])
```

- [ ] **Step 4: Implement atomic render and exact ffprobe validation**

`Renderer.render` refuses to overwrite an existing final path unless `overwrite=True`; writes `<name>.partial.mp4`; deletes the partial on cancellation; executes FFmpeg; validates the partial; then `os.replace`s it to final. A failed command raises `OutputValidationFailed` with only the last 1,000 stderr characters.

`OutputValidator` calls ffprobe JSON and requires:

- format includes `mp4` or `mov` and start time is at least −0.001 seconds;
- one H.264 video stream, exactly 1080×1920, `yuv420p`, average frame rate 30 ±0.01;
- one AAC stream;
- positive duration.

Return `OutputProbe` with codec/dimensions/fps/duration/start/audio fields. Any violation raises `PipelineError(ErrorCode.OUTPUT_VALIDATION_FAILED, "rendered output violates platform contract", context={"violations": violations, "filename": path.name})`.

- [ ] **Step 5: Implement manifest checksums and warning provenance**

Write `outputs/manifest.json` atomically after each completed variant. Include schema version 1, app version, source IDs/fingerprints (not full paths), analyzer/composer/audio preset versions, timeline revisions, output filename, full SHA-256, `OutputProbe`, elapsed seconds, and warning codes. Redact paths from shareable diagnostic data.

- [ ] **Step 6: Add a real vertical-output integration test**

Use two generated source clips with distinct colors and tones, a three-item timeline at 1×/2×/12×, a center crop, silent AAC if the audio plan is silent, and a watermark. Render through `h264_videotoolbox`, validate with the real `OutputValidator`, decode frames near each join to prove no black gap, and compare first/last audio PTS to video PTS for drift below 100 ms. Mark `media` and skip only for missing backend/filter support.

- [ ] **Step 7: Run render tests and static checks**

```bash
.venv/bin/pytest tests/unit/render -q
.venv/bin/pytest tests/integration/render/test_vertical_output.py -m media -q
.venv/bin/ruff check src/kem_timelapse/render tests/unit/render tests/integration/render
.venv/bin/mypy src/kem_timelapse/render
```

Expected: unit tests pass; media integration passes or intentionally skips with backend reason; static checks exit 0.

- [ ] **Step 8: Commit rendering and validation**

```bash
git add src/kem_timelapse/render tests/unit/render tests/integration/render
git commit -m "feat: render and validate platform-ready vertical videos"
```

### Task 13: Resumable job orchestration, structured logs, cancel, and internal CLI

**Files:**
- Create: `src/kem_timelapse/jobs/state_machine.py`
- Create: `src/kem_timelapse/jobs/cancellation.py`
- Create: `src/kem_timelapse/jobs/events.py`
- Create: `src/kem_timelapse/jobs/runner.py`
- Create: `src/kem_timelapse/cli.py`
- Create: `tests/unit/jobs/test_state_machine.py`
- Create: `tests/unit/jobs/test_runner.py`
- Create: `tests/unit/jobs/test_events.py`
- Create: `tests/integration/jobs/test_resume.py`

**Interfaces:**
- Consumes: repositories and all stage services from Tasks 2–12.
- Produces: `CancellationToken`, `JobEvent`, `JsonlEventSink`, `transition(state, target)`, `JobStages`, `JobRunner(repository: ProjectRepository, stages: JobStages, token: CancellationToken | None = None, checkpoint_hook: Callable[[str], None] | None = None)`, `JobRunner.analyze_to_review`, `JobRunner.render_pack`, and Typer commands `inspect`, `analyze`, `render`.

- [ ] **Step 1: Write failing transition and render-resume tests**

```python
# tests/unit/jobs/test_state_machine.py
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
```

```python
# tests/unit/jobs/test_runner.py
from pathlib import Path

from kem_timelapse.domain.models import JobStatus, ProjectState, Variant
from kem_timelapse.jobs.runner import JobRunner
from kem_timelapse.storage.project_repository import ProjectRepository


class FakeStages:
    def __init__(self) -> None:
        self.rendered: list[Variant] = []

    def prepare_audio(self) -> None:
        return None

    def selected_clip_ids(self) -> list[str]:
        return []

    def analysis_artifact_is_valid(self, clip_id: str) -> bool:
        return False

    def analyze_clip(self, clip_id: str, token: object) -> None:
        raise AssertionError("render-only test must not analyze")

    def compose_timelines(self) -> None:
        raise AssertionError("render-only test must not compose")

    def output_is_valid(self, variant: Variant) -> bool:
        return variant is Variant.TIKTOK_FAST or variant in self.rendered

    def render_variant(self, variant: Variant) -> None:
        self.rendered.append(variant)


def test_render_resume_skips_completed_tiktok(tmp_path: Path) -> None:
    repository = ProjectRepository(tmp_path / "project")
    repository.create(ProjectState(
        project_id="p", name="Art", status=JobStatus.RENDERING,
        completed_variants=[Variant.TIKTOK_FAST],
    ))
    stages = FakeStages()
    JobRunner(repository, stages).render_pack()
    assert stages.rendered == [Variant.REELS_AESTHETIC, Variant.SHORTS_ASMR]
    assert repository.load_state().status is JobStatus.COMPLETED
```

- [ ] **Step 2: Run tests and verify missing-module failures**

Run: `.venv/bin/pytest tests/unit/jobs -q`

Expected: collection fails because `kem_timelapse.jobs` is absent.

- [ ] **Step 3: Implement the explicit state graph and cancellation token**

Allowed transitions:

```python
ALLOWED = {
    JobStatus.NEW: {JobStatus.INGESTED, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.INGESTED: {JobStatus.ANALYZING, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.ANALYZING: {JobStatus.REVIEW_READY, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.REVIEW_READY: {JobStatus.RENDERING, JobStatus.ANALYZING, JobStatus.CANCELLED},
    JobStatus.RENDERING: {JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.CANCELLED: {JobStatus.ANALYZING, JobStatus.RENDERING},
    JobStatus.FAILED: {JobStatus.ANALYZING, JobStatus.RENDERING},
    JobStatus.COMPLETED: {JobStatus.RENDERING},
}
```

`CancellationToken` wraps `threading.Event` and exposes `cancel()`, `is_set()`, `wait(timeout: float) -> bool`, and `raise_if_cancelled()`. A cancel writes `status=Cancelled` and `resume_from` equal to the active long stage only after the child process has terminated and partial files are removed.

- [ ] **Step 4: Implement redacted structured JSONL events**

`JobEvent` fields are `timestamp`, `project_id`, `stage`, `event`, optional `clip_id`, optional `variant`, `progress` 0–1, optional warning/error code, and `details`. `JsonlEventSink.emit` appends one JSON line under a lock and fsyncs. Before writing, recursively replace values of keys `path`, `source_path`, and `music_path` with `<redacted>`. Unit-test that tracebacks remain in local details but source paths do not.

- [ ] **Step 5: Implement analysis and render checkpoint orchestration**

Define the orchestration boundary so unit tests do not invoke media binaries:

```python
class JobStages(Protocol):
    def selected_clip_ids(self) -> Sequence[str]:
        raise NotImplementedError

    def analysis_artifact_is_valid(self, clip_id: str) -> bool:
        raise NotImplementedError

    def analyze_clip(self, clip_id: str, token: CancellationToken) -> None:
        raise NotImplementedError

    def compose_timelines(self) -> None:
        raise NotImplementedError

    def prepare_audio(self) -> None:
        raise NotImplementedError

    def output_is_valid(self, variant: Variant) -> bool:
        raise NotImplementedError

    def render_variant(self, variant: Variant) -> None:
        raise NotImplementedError
```

The concrete `PipelineStages` adapter wires preflight, proxy, analyzer, segmenter, composers, audio, framing, renderer, validator, and manifest services from Tasks 2–12. `JobRunner` contains only ordering, state, checkpoint, cancel, and error policy.

`analyze_to_review` performs preflight, proxies and analysis one selected clip at a time. The analysis artifact key is SHA-256 over source fingerprint, proxy version, analyzer version, analysis preset version, and serialized ROI override. Reuse a completed clip only when this key and the JSON schema match; otherwise remove its ID from `completed_analysis_clip_ids` and recompute. After each clip, write its analysis JSON atomically, append clip ID to `completed_analysis_clip_ids`, and save state. Then combine segments, compose/save three timelines, and transition to `ReviewReady`.

`render_pack` validates all source fingerprints and timelines, transitions to `Rendering`, prepares shared audio ranges, then renders variants strictly in TikTok → Reels → Shorts order. After each validated atomic output, append to `completed_variants`, update manifest and save state. Resume skips a clip/variant only when both checkpoint state and artifact validation agree; otherwise invalidate that checkpoint and rerun it.

Catch `InterruptedError` as Cancelled. Catch `PipelineError` as Failed while preserving its code/context. For Cancelled and Failed, set `resume_from` to `Analyzing` or `Rendering` according to the active stage. Unexpected exceptions become Failed and include a local traceback event. Never swallow an error or transition to Completed unless all three outputs validate.

- [ ] **Step 6: Add crash-injection integration tests**

Inject a `checkpoint_hook(name: str) -> None` into `JobRunner` for tests. Raise `RuntimeError` after first analysis clip and after TikTok atomic output, reconstruct `JobRunner` from disk, and prove:

- completed analysis clip is not analyzed twice;
- a partial artifact is removed or ignored;
- validated TikTok is not rendered twice;
- final state reaches Completed with three validated outputs;
- original source size, mtime, and fingerprint remain identical.

Use a `SimulatedCrash(BaseException)` in the integration test so normal application exception handling cannot convert the injected process death into `Failed`. The test hook is exact and fires only after the named atomic checkpoint:

```python
class SimulatedCrash(BaseException):
    pass


def crash_after(expected_name: str):
    fired = False

    def hook(name: str) -> None:
        nonlocal fired
        if name == expected_name and not fired:
            fired = True
            raise SimulatedCrash(name)

    return hook


def test_resume_after_analysis_and_tiktok_checkpoints(project_with_two_clips, counting_stages) -> None:
    repository, sources_before = project_with_two_clips
    with pytest.raises(SimulatedCrash):
        JobRunner(repository, counting_stages, checkpoint_hook=crash_after("analysis:clip-1")).analyze_to_review()
    JobRunner(repository, counting_stages).analyze_to_review()
    assert counting_stages.analysis_calls.count("clip-1") == 1

    with pytest.raises(SimulatedCrash):
        JobRunner(repository, counting_stages, checkpoint_hook=crash_after("render:tiktok-fast")).render_pack()
    JobRunner(repository, counting_stages).render_pack()
    assert counting_stages.render_calls.count(Variant.TIKTOK_FAST) == 1
    assert repository.load_state().status is JobStatus.COMPLETED
    assert [source_snapshot(path) for path in counting_stages.source_paths] == sources_before
```

`project_with_two_clips`, `counting_stages`, and `source_snapshot` are defined in the same integration file: the fixture creates two temp sources, stores `(size, mtime_ns, fingerprint_source(path))`, and the fake stage writes atomic analysis/output artifacts while recording calls. It also writes a `.partial.mp4` before the injected render crash so resume proves the partial is removed or ignored.

- [ ] **Step 7: Add diagnostic CLI over the same services**

Use Typer commands:

```text
kem-timelapse inspect PROJECT_DIR
kem-timelapse analyze PROJECT_DIR --source SOURCE  # repeat --source for additional clips
kem-timelapse render PROJECT_DIR [--overwrite]
```

`inspect` prints state, completed clips/variants, and warning codes as JSON. Commands return exit code 2 for blocking `PipelineError`, 130 for cancellation, and 1 for unexpected failures. The CLI imports no PySide6 module. Add this boundary test:

```python
# tests/unit/jobs/test_core_boundary.py
import ast
from pathlib import Path


def test_core_never_imports_pyside6() -> None:
    violations: list[str] = []
    for path in Path("src/kem_timelapse").rglob("*.py"):
        if "ui" in path.relative_to("src/kem_timelapse").parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name == "PySide6" or name.startswith("PySide6.") for name in names):
                violations.append(str(path))
    assert violations == []
```

- [ ] **Step 8: Run job, resume, CLI, and static checks**

```bash
.venv/bin/pytest tests/unit/jobs tests/integration/jobs -q
.venv/bin/pytest tests/unit -q
.venv/bin/ruff check src tests/unit tests/integration/jobs
.venv/bin/mypy src/kem_timelapse
```

Expected: all non-media unit/integration tests pass; Ruff and mypy exit 0.

- [ ] **Step 9: Commit the resumable application core**

```bash
git add src/kem_timelapse/jobs src/kem_timelapse/cli.py tests/unit/jobs tests/integration/jobs
git commit -m "feat: orchestrate resumable analysis and Content Pack render"
```

### Task 14: Three-step PySide6 desktop shell and background analysis

**Files:**
- Create: `src/kem_timelapse/ui/app.py`
- Create: `src/kem_timelapse/ui/main_window.py`
- Create: `src/kem_timelapse/ui/controller.py`
- Create: `src/kem_timelapse/ui/worker.py`
- Create: `src/kem_timelapse/ui/source_page.py`
- Create: `src/kem_timelapse/ui/analysis_page.py`
- Create: `tests/unit/ui/test_main_window.py`
- Create: `tests/unit/ui/test_controller.py`

**Interfaces:**
- Consumes: `JobRunner`, `ProjectRepository`, `IngestService`, `PipelineError`, `JobEvent`; imports PySide6 only inside `ui/`.
- Produces: `main()`, `MainWindow`, `DesktopController`, `SourcePage`, `AnalysisPage`, and a cancellable `JobWorker` running core work off the GUI thread.

- [ ] **Step 1: Write failing UI smoke and three-step navigation tests**

```python
# tests/unit/ui/test_main_window.py
from PySide6.QtCore import Qt

from kem_timelapse.ui.main_window import MainWindow


def test_window_starts_on_source_and_exposes_three_steps(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == "Kem Timelapse Studio"
    assert window.stack.currentWidget().objectName() == "sourcePage"
    assert [button.text() for button in window.step_buttons] == [
        "1. Nguồn quay", "2. Phân tích", "3. Preview & Render"
    ]
    assert window.analyze_button.isEnabled() is False


def test_source_drop_enables_analyze_after_validation(qtbot, tmp_path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    source = tmp_path / "clip.MOV"
    source.write_bytes(b"fixture")
    window.source_page.add_paths([source])
    assert window.analyze_button.isEnabled() is False
    window.source_page.set_probe_result(source, valid=True, summary="00:01 · 4K/30")
    assert window.source_page.source_count() == 1
    assert window.analyze_button.isEnabled() is True
```

- [ ] **Step 2: Run UI tests headlessly and verify the missing-module failure**

Run:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/ui/test_main_window.py -q
```

Expected: collection fails because `kem_timelapse.ui` is absent.

- [ ] **Step 3: Implement the window shell and source page**

`MainWindow` is a `QMainWindow` containing:

- a fixed top row of three non-checkable step buttons used as status indicators;
- a `QStackedWidget` with `SourcePage`, `AnalysisPage`, and a placeholder `QWidget` named `previewPage` until Task 15;
- Back, Analyze, Cancel, and Continue/Render action buttons with stable `objectName` values;
- a bottom status label for blocking error/warning summaries.

`SourcePage` accepts drag/drop and file dialog selections for `.mov`/`.mp4` case-insensitively, expands a dropped directory only one level, removes duplicates by resolved path, shows name/duration/format after probe, supports drag reorder and checkboxes, output folder selection, optional music selection, and rights confirmation. It emits `sourcesChanged(list[Path])`. The controller rewrites `SourceClip.order`/`selected` and calls `ProjectRepository.save_sources` after every reorder or checkbox change. It must not run ffprobe on the GUI thread; initially display “Đang đọc…” and let the controller update rows.

Use these object names so tests and accessibility remain stable:

```python
self.setObjectName("sourcePage")
self.source_list.setObjectName("sourceList")
self.add_button.setObjectName("addSourcesButton")
self.output_button.setObjectName("chooseOutputButton")
self.music_button.setObjectName("chooseMusicButton")
self.rights_checkbox.setObjectName("musicRightsCheckbox")
```

- [ ] **Step 4: Implement Qt worker/controller without leaking core dependencies into views**

`JobWorker(QObject)` is constructed as `JobWorker(operation: Callable[[CancellationToken], object], token: CancellationToken)`. It has signals `progress(object)`, `completed(object)`, `failed(object)`, and `cancelled()`. Its `run()` slot calls `operation(token)`. Its `cancel()` slot triggers the shared token.

`DesktopController` owns repositories/services and connects view signals. It moves each `JobWorker` to a fresh `QThread`; connects thread start → worker run and every terminal signal → thread quit/delete. It maps `PipelineError.code/context` to Vietnamese UI copy while retaining diagnostic detail in JSONL. It never calls `QApplication.processEvents()` in a loop.

Provide deterministic mappings:

```python
ERROR_COPY = {
    "SourceUnavailable": "Không đọc được video nguồn. Hãy kết nối lại ổ hoặc chọn lại file.",
    "InsufficientDisk": "Không đủ dung lượng cho cache và ba video đầu ra.",
    "RenderBackendUnavailable": "FFmpeg hoặc VideoToolbox chưa sẵn sàng.",
    "OutputNotWritable": "Không thể ghi vào thư mục đầu ra đã chọn.",
    "TimelineInvalid": "Timeline cần được sửa trước khi render.",
    "OutputValidationFailed": "Video render chưa đạt chuẩn đầu ra.",
}


def user_message(error: PipelineError) -> str:
    return ERROR_COPY[error.code.value]
```

- [ ] **Step 5: Add controller tests for progress, cancellation, and errors**

Use fake services gated by `threading.Event`. Add at least this cancellation/error contract:

```python
# tests/unit/ui/test_controller.py
import threading

from PySide6.QtCore import QThread

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.jobs.cancellation import CancellationToken
from kem_timelapse.ui.controller import ERROR_COPY, user_message
from kem_timelapse.ui.worker import JobWorker


def start_worker_thread(worker: JobWorker) -> QThread:
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.completed.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.cancelled.connect(thread.quit)
    thread.start()
    return thread


def test_worker_cancel_sets_token_and_emits_cancelled(qtbot) -> None:
    entered = threading.Event()
    token = CancellationToken()

    def operation(active_token: CancellationToken) -> object:
        entered.set()
        while not active_token.is_set():
            active_token.wait(0.01)
        active_token.raise_if_cancelled()
        return object()

    worker = JobWorker(operation, token)
    thread = start_worker_thread(worker)
    assert entered.wait(timeout=1)
    with qtbot.waitSignal(worker.cancelled, timeout=1_000):
        worker.cancel()
    assert token.is_set()
    thread.quit()
    assert thread.wait(5_000)


def test_controller_maps_blocking_error_without_leaking_context() -> None:
    error = PipelineError(
        ErrorCode.OUTPUT_NOT_WRITABLE,
        "permission denied at /private/output",
        context={"path": "/private/output"},
    )
    message = user_message(error)
    assert message == ERROR_COPY["OutputNotWritable"]
    assert "/private/output" not in message
```

Add separate assertions that progress updates do not block a zero-delay Qt timer, closing the window requests cancel, and the worker thread joins within 5 seconds.

- [ ] **Step 6: Run UI, core-boundary, and static checks**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/ui -q
.venv/bin/pytest tests/unit/jobs -q
.venv/bin/ruff check src/kem_timelapse/ui tests/unit/ui
.venv/bin/mypy src/kem_timelapse/ui
```

Expected: all UI/job tests pass without a display server; static checks exit 0.

- [ ] **Step 7: Commit the desktop analysis workflow**

```bash
git add src/kem_timelapse/ui tests/unit/ui
git commit -m "feat: add desktop import and analysis workflow"
```

### Task 15: Proxy preview, variant editing, manual ROI, and render controls

**Files:**
- Create: `src/kem_timelapse/ui/preview_page.py`
- Create: `src/kem_timelapse/ui/timeline_model.py`
- Create: `src/kem_timelapse/ui/roi_overlay.py`
- Create: `tests/unit/ui/conftest.py`
- Create: `tests/unit/ui/test_preview_page.py`
- Create: `tests/unit/ui/test_timeline_model.py`
- Modify: `src/kem_timelapse/ui/main_window.py`
- Modify: `src/kem_timelapse/ui/controller.py`

**Interfaces:**
- Consumes: three `EditingSession` values, proxies, `TrackedRoi`/manual `Roi`, warning list, `JobRunner.render_pack`.
- Produces: `PreviewPage`, `TimelineTableModel`, `RoiOverlay`; emits typed edit requests and render/cancel events.

- [ ] **Step 1: Write failing tests for variant isolation and render blocking**

```python
# tests/unit/ui/conftest.py
import pytest

from kem_timelapse.domain.models import Timeline, TimelineItem, Variant
from kem_timelapse.editing.session import EditingSession


@pytest.fixture
def editing_sessions() -> dict[Variant, EditingSession]:
    return {
        variant: EditingSession(Timeline(
            variant=variant,
            revision=0,
            audio_mode="asmr_music" if variant is not Variant.SHORTS_ASMR else "asmr",
            items=[TimelineItem(
                id=f"{variant.value}-body-shared-0", role="body", segment_id="shared",
                trim_in_ms=0, trim_out_ms=4_000, speed=4,
            )],
        ))
        for variant in Variant
    }
```

```python
# tests/unit/ui/test_preview_page.py
from PySide6.QtCore import QObject, Qt

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Variant
from kem_timelapse.ui.preview_page import PreviewPage


def test_variant_switch_preserves_independent_edits(qtbot, editing_sessions) -> None:
    page = PreviewPage()
    qtbot.addWidget(page)
    page.set_sessions(editing_sessions)
    page.select_variant(Variant.TIKTOK_FAST)
    page.timeline_view.selectRow(0)
    page.speed_combo.setCurrentText("2×")
    assert editing_sessions[Variant.TIKTOK_FAST].snapshot().items[0].speed == 2
    assert editing_sessions[Variant.REELS_AESTHETIC].snapshot().items[0].speed != 2


def test_low_roi_confidence_blocks_render_until_manual_confirmation(qtbot) -> None:
    page = PreviewPage()
    qtbot.addWidget(page)
    page.set_warnings([WarningCode.LOW_ROI_CONFIDENCE])
    assert page.render_pack_button.isEnabled() is False
    page.roi_overlay.set_manual_points([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)])
    qtbot.mouseClick(page.confirm_roi_button, Qt.LeftButton)
    assert page.render_pack_button.isEnabled() is True
```

- [ ] **Step 2: Run focused tests and verify missing-module failures**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/ui/test_preview_page.py -q`

Expected: collection fails because preview components are absent.

- [ ] **Step 3: Implement a minimal, accessible timeline model**

`TimelineTableModel(QAbstractTableModel)` exposes columns Keep, Label, Source Time, Speed, Reason. Use `Qt.CheckStateRole` for Keep and `Qt.EditRole` for speed. `setData` emits a `SetKeep` or `SetSpeed` command through an injected callback; it does not mutate Pydantic models itself. Segment colors are presentation-only: inactive gray, broad fill blue, progress indigo, detail purple, ASMR teal, hook/reveal green. Tooltips display `reason_codes` in Vietnamese-friendly phrases.

Add this exact model contract test:

```python
# tests/unit/ui/test_timeline_model.py
from PySide6.QtCore import Qt

from kem_timelapse.domain.models import Variant
from kem_timelapse.editing.commands import SetKeep, SetSpeed
from kem_timelapse.ui.timeline_model import TimelineTableModel


def test_timeline_model_emits_commands_without_mutating_session(editing_sessions) -> None:
    session = editing_sessions[Variant.TIKTOK_FAST]
    commands: list[object] = []
    model = TimelineTableModel(session.snapshot(), segment_lookup={}, on_edit=commands.append)
    keep_index = model.index(0, model.KEEP_COLUMN)
    speed_index = model.index(0, model.SPEED_COLUMN)
    assert model.rowCount() == 1
    assert model.flags(keep_index) & Qt.ItemIsUserCheckable
    assert model.flags(speed_index) & Qt.ItemIsEditable
    assert model.setData(keep_index, Qt.Unchecked, Qt.CheckStateRole)
    assert model.setData(speed_index, 2, Qt.EditRole)
    assert commands == [
        SetKeep(item_id="tiktok-fast-body-shared-0", keep=False),
        SetSpeed(item_id="tiktok-fast-body-shared-0", speed=2),
    ]
    assert session.snapshot().items[0].keep is True
    assert session.snapshot().items[0].speed == 4
```

- [ ] **Step 4: Implement proxy playback and ROI overlay**

Use `QMediaPlayer` + `QAudioOutput` for the proxy and a `QVideoWidget` under a transparent `RoiOverlay`. The overlay stores four normalized clockwise points, supports dragging each handle, clamps to [0,1], rejects self-intersecting quads, and emits `roiConfirmed(Roi)` only from the Confirm button. Playback seeks to selected segment start using the proxy/source timestamp identity.

The preview page contains:

- variant tabs “TikTok Fast”, “Reels Aesthetic”, “Shorts ASMR” with proposed duration;
- 9:16 preview viewport;
- timeline table and Keep/Delete, 1×/2×/4×/12× controls;
- Undo, Redo, Copy to all;
- watermark text/opacity/position controls;
- warning banner and manual ROI confirm;
- “Render TikTok trước” and “Render đủ Content Pack” actions.

No generic multi-track, free transitions, color grading, captions, or upload controls.

- [ ] **Step 5: Connect edits, debounced persistence, and rendering**

The controller builds one `EditingSession` per variant. UI commands call `session.apply`; Undo/Redo call the session methods; Copy to all uses `copy_shared_edits`. Persist accepted snapshots after a 300 ms single-shot `QTimer`, but immediately persist before render. Render controls are disabled when no timelines exist, manual ROI is unresolved, output is unwritable, or a worker is active.

Show per-variant progress and mark a completed output clickable with `QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path)))`. TikTok completion must appear while Reels/Shorts continue. Cancellation preserves already validated outputs and presents “Có thể tiếp tục từ checkpoint”.

- [ ] **Step 6: Add UI regressions for the approved editing surface**

Add concrete table-driven UI checks:

```python
import pytest


@pytest.mark.parametrize(("label", "speed"), [("1×", 1), ("2×", 2), ("4×", 4), ("12×", 12)])
def test_all_approved_speeds_round_trip(qtbot, editing_sessions, label: str, speed: int) -> None:
    page = PreviewPage()
    qtbot.addWidget(page)
    page.set_sessions(editing_sessions)
    page.select_variant(Variant.TIKTOK_FAST)
    page.timeline_view.selectRow(0)
    page.speed_combo.setCurrentText(label)
    assert editing_sessions[Variant.TIKTOK_FAST].snapshot().items[0].speed == speed
    page.undo_button.click()
    assert editing_sessions[Variant.TIKTOK_FAST].snapshot().items[0].speed == 4
    page.redo_button.click()
    assert editing_sessions[Variant.TIKTOK_FAST].snapshot().items[0].speed == speed


def test_preview_defaults_and_stable_controls(qtbot) -> None:
    page = PreviewPage()
    qtbot.addWidget(page)
    assert page.watermark_text.text() == "@kem12032024"
    assert page.watermark_opacity.value() == 30
    assert {widget.objectName() for widget in page.findChildren(QObject)} >= {
        "variantTabs", "proxyVideo", "timelineView", "undoButton", "redoButton",
        "copyToAllButton", "confirmRoiButton", "renderFirstButton", "renderPackButton",
    }
```

Add `QSignalSpy` assertions that Keep/Delete emits `SetKeep`, Copy to all changes only matching `(role, segment_id)`, invalid self-intersecting ROI emits no confirmation, render requests arrive TikTok → Reels → Shorts, completed output links use local file URLs, and cancel/resume text is exactly “Có thể tiếp tục từ checkpoint”.

- [ ] **Step 7: Run the full UI test set and static checks**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/ui -q
.venv/bin/ruff check src/kem_timelapse/ui tests/unit/ui
.venv/bin/mypy src/kem_timelapse/ui
```

Expected: all UI tests pass headlessly; static checks exit 0.

- [ ] **Step 8: Commit preview and render controls**

```bash
git add src/kem_timelapse/ui tests/unit/ui
git commit -m "feat: add editable Content Pack preview and render controls"
```

### Task 16: Golden quality metrics and full-recording benchmark harness

**Files:**
- Create: `src/kem_timelapse/quality/metrics.py`
- Create: `src/kem_timelapse/quality/report.py`
- Create: `tools/generate_test_media.py`
- Create: `tools/benchmark.py`
- Create: `tests/fixtures/golden/labels.json`
- Create: `tests/unit/quality/test_metrics.py`
- Create: `tests/e2e/test_acceptance_recording.py`
- Create: `docs/benchmarking.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: labeled source ranges, canonical segments, output probe/manifest, stage timing events, private acceptance source path.
- Produces: `QualityReport`, `compute_quality(labels: Sequence[LabeledRange], decisions: Sequence[LabeledRange]) -> QualityReport`, benchmark JSON/Markdown report, and one E2E acceptance test.

- [ ] **Step 1: Write failing quality-metric boundary tests**

```python
# tests/unit/quality/test_metrics.py
from kem_timelapse.quality.metrics import LabeledRange, compute_quality


def test_quality_uses_duration_overlap_not_segment_count() -> None:
    labels = [
        LabeledRange(source_id="a", start_ms=0, end_ms=10_000, label="inactive"),
        LabeledRange(source_id="a", start_ms=10_000, end_ms=20_000, label="important_detail"),
    ]
    decisions = [
        LabeledRange(source_id="a", start_ms=0, end_ms=8_000, label="deleted"),
        LabeledRange(source_id="a", start_ms=10_000, end_ms=19_000, label="kept"),
    ]
    report = compute_quality(labels, decisions)
    assert report.inactivity_removed == 0.80
    assert report.important_detail_retained == 0.90
    assert report.passes_quality_gate is True
```

- [ ] **Step 2: Run the test and verify the missing-module failure**

Run: `.venv/bin/pytest tests/unit/quality/test_metrics.py -q`

Expected: collection fails because `kem_timelapse.quality` is absent.

- [ ] **Step 3: Implement interval-overlap quality calculations**

`LabeledRange` validates positive ranges and labels from `inactive`, `important_detail`, `deleted`, `kept`. Compute intersections by source ID using a two-pointer sorted interval walk. Define:

```text
inactivity_removed = deleted ∩ labeled_inactive duration / labeled_inactive duration
important_detail_retained = kept ∩ labeled_important_detail duration / labeled_important_detail duration
passes_quality_gate = inactivity_removed >= 0.80 and important_detail_retained >= 0.90
```

Zero denominator is an invalid benchmark and raises `ValueError`, never an automatic pass. `QualityReport` also stores the numerator/denominator milliseconds for auditability.

- [ ] **Step 4: Add deterministic generated fixtures and golden labels**

`tools/generate_test_media.py` uses FFmpeg and OpenCV to create a 60-second 4K/30 SDR source assembled from: 10 s static, 15 s broad fill, 10 s static, 15 s detail strokes with 6 kHz brush bursts, 5 s tracker occlusion, 5 s clean reveal. It writes media under ignored `tests/generated_media/` and committed labels under `tests/fixtures/golden/labels.json`. Include a second clip with 90° rotation metadata and one no-audio clip.

The generator accepts `--force`, prints SHA-256 for each fixture, and is deterministic for a fixed OpenCV/FFmpeg toolchain. Unit/integration tests consume labels; generated binary media is never committed.

- [ ] **Step 5: Implement benchmark CLI and report schema**

`tools/benchmark.py` accepts:

```text
--source PATH --labels PATH --project-dir PATH --report PATH  # --source is repeatable
```

It runs the same `JobRunner`, records wall-clock stage durations, source/codec/duration, app/FFmpeg versions, free disk, volume type, output probes, warning codes, quality metrics, time-to-first-output, and full-pack time. It writes schema-versioned JSON and a concise Markdown summary. It returns nonzero when any output/quality/time gate fails.

Do not collect serial numbers, usernames, full source paths, or media samples. Record power source and macOS-reported thermal state only when obtainable without elevated permission; otherwise record `not_available` as a valid measured state, not an unfinished field.

- [ ] **Step 6: Add the private full-recording E2E test**

Read `KEM_TIMELAPSE_ACCEPTANCE_SOURCE` and `KEM_TIMELAPSE_ACCEPTANCE_LABELS`. If absent, skip with “private acceptance recording not configured”. When present, require macOS Apple Silicon, run import → analysis → three timelines → one manual edit → render; inject one analysis restart and one post-TikTok restart; then assert:

- source stat/fingerprint unchanged;
- three validated H.264/AAC 1080×1920/30 outputs and manifest entries;
- no black-gap scan finding and A/V drift under 100 ms;
- inactivity removal at least 0.80 and important detail retention at least 0.90;
- preview edit interaction timer at most 5 minutes when run in supervised acceptance mode;
- first output at most 900 seconds and full pack at most 1,200 seconds on M3 Pro ≥24 GB.

Mark `e2e`; never run it in ordinary CI without both environment variables.

- [ ] **Step 7: Ignore private/generated media and document benchmark execution**

Add:

```gitignore
tests/generated_media/
tests/private_media/
benchmark-results/
```

`docs/benchmarking.md` must give exact generate, unit/integration, and private E2E commands; explain that retention >65% is evaluated after posting and is absent from renderer acceptance.

- [ ] **Step 8: Run quality tests and a generated-media dry benchmark**

```bash
.venv/bin/pytest tests/unit/quality -q
.venv/bin/python tools/generate_test_media.py --force
.venv/bin/pytest tests/integration -m media -q
.venv/bin/pytest tests/e2e -m e2e -q
```

Expected: quality and generated-media tests pass; private E2E reports one intentional skip until the real recording/labels are configured.

- [ ] **Step 9: Commit quality and benchmark tooling**

```bash
git add .gitignore src/kem_timelapse/quality tools tests/fixtures/golden tests/unit/quality tests/e2e docs/benchmarking.md
git commit -m "test: add media quality and performance acceptance harness"
```

### Task 17: Unsigned macOS app packaging, operator documentation, and release verification

**Files:**
- Create: `packaging/kem-timelapse.spec`
- Create: `scripts/build_macos.sh`
- Create: `scripts/smoke_app.py`
- Create: `README.md`
- Create: `docs/operator-guide.md`
- Create: `docs/third-party-licenses.md`
- Create: `tests/integration/packaging/test_built_app.py`
- Modify: `src/kem_timelapse/ui/app.py`

**Interfaces:**
- Consumes: the complete application and external `ffmpeg`/`ffprobe` preflight.
- Produces: unsigned `dist/Kem Timelapse Studio.app`, operator setup/run instructions, smoke-test exit path, and dependency-license inventory.

- [ ] **Step 1: Write a failing app-entry smoke test**

```python
# tests/integration/packaging/test_built_app.py
import os
import subprocess
from pathlib import Path

import pytest


def test_built_app_passes_headless_smoke_check() -> None:
    executable = Path("dist/Kem Timelapse Studio.app/Contents/MacOS/Kem Timelapse Studio")
    if not executable.exists():
        pytest.skip("unsigned app bundle has not been built")
    environment = os.environ | {"QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run([str(executable), "--smoke-test"], env=environment, capture_output=True, text=True)
    assert result.returncode == 0
    assert "SMOKE_OK" in result.stdout
```

- [ ] **Step 2: Run the packaging test and confirm the intentional pre-build skip**

Run: `.venv/bin/pytest tests/integration/packaging/test_built_app.py -q`

Expected: one skip stating the app bundle has not been built.

- [ ] **Step 3: Add a deterministic headless app smoke path**

Update `ui.app.main` so `--smoke-test` creates `QApplication`, constructs `MainWindow`, verifies the three pages and that no core module imported PySide6, prints `SMOKE_OK`, closes the window, and exits 0 without starting the event loop or accessing media/network. Ordinary launch starts `app.exec()`.

- [ ] **Step 4: Define the PyInstaller bundle and build script**

`packaging/kem-timelapse.spec` bundles `src/kem_timelapse`, PySide6 multimedia plugins, OpenCV, Pydantic, and optional DeepFilterNet modules when installed. It does not bundle source/test media. The bundle identifier is `com.kem12032024.timelapse`, app name is `Kem Timelapse Studio`, target architecture is `arm64`, and signing identity is unset.

`scripts/build_macos.sh` must use `set -euo pipefail`, reject non-Darwin/non-arm64 hosts, run unit/non-private integration tests, Ruff and mypy, clean `build/` and the named app bundle only, invoke `.venv/bin/pyinstaller packaging/kem-timelapse.spec --noconfirm`, then run the built executable with `--smoke-test`. Do not delete arbitrary `dist/` contents.

- [ ] **Step 5: Document exact operator workflow and prerequisites**

`README.md` covers environment creation, editable install, `brew install ffmpeg`, optional DeepFilterNet install, CLI diagnostics, desktop launch, tests, and unsigned build. `docs/operator-guide.md` covers Import → Analyze → Preview → Render, manual ROI, rights confirmation, warning meanings, resume after Force Quit, output filenames, cache cleanup, and how to export redacted diagnostics.

`docs/third-party-licenses.md` records dependency name, project URL, installed version command, license identifier, redistribution note, and whether it is bundled. Treat incomplete or incompatible redistribution review as a release blocker; the document must not assert approval that has not been verified.

- [ ] **Step 6: Run the complete non-private verification suite**

```bash
.venv/bin/pytest -m 'not e2e' -q
.venv/bin/ruff check src tests tools
.venv/bin/mypy src/kem_timelapse
bash scripts/build_macos.sh
.venv/bin/pytest tests/integration/packaging/test_built_app.py -q
```

Expected: all non-private tests pass; Ruff/mypy exit 0; unsigned `.app` builds; smoke test passes. Media tests may skip only with an explicit missing-backend reason, which blocks declaring the media-capable MVP complete on the acceptance Mac.

- [ ] **Step 7: Run supervised private acceptance before an MVP release tag**

```bash
KEM_TIMELAPSE_ACCEPTANCE_SOURCE='/absolute/path/to/real-recording.MOV' \
KEM_TIMELAPSE_ACCEPTANCE_LABELS='/absolute/path/to/labels.json' \
.venv/bin/pytest tests/e2e/test_acceptance_recording.py -m e2e -v
```

Expected: one pass with all quality/performance/output gates. If the recording is not yet available, report the release as “implementation verified on generated fixtures; private acceptance pending” and do not claim the 15/20-minute or 80/90% gates.

- [ ] **Step 8: Commit packaging and operator handoff**

```bash
git add packaging scripts README.md docs/operator-guide.md docs/third-party-licenses.md src/kem_timelapse/ui/app.py tests/integration/packaging
git commit -m "build: package the unsigned macOS desktop application"
```

## Spec coverage map

| Approved requirement | Implementation and proof |
|---|---|
| Local Python 3.10+ macOS desktop, core independent of UI | Tasks 1, 13, 14; AST boundary test forbids PySide6 outside `ui/` |
| MOV/MP4 ingest, metadata/rotation, folder ordering, immutable source | Tasks 2–4, 14; fingerprint/stat assertions in Task 13 and E2E |
| Proxy-first, two-pass heuristic analysis | Tasks 4–7; generated static/broad/detail/ASMR fixtures |
| Delete inactivity; 1×/2×/4×/12× pacing | Tasks 1, 7–9; segment and composer boundary tests |
| Analyze once; TikTok/Reels/Shorts tailored Content Pack | Task 8; three independent duration/selection contracts |
| Minimal preview, Keep/Delete, speed, crop, watermark, Undo/Redo, Copy to all | Tasks 9, 14, 15; headless Qt interaction tests |
| DeepFilterNet selected ranges, FFmpeg fallback, ASMR EQ/dynamics | Task 10; fake fallback unit test and golden audio test |
| Local rights-confirmed music, ducking, −14 LUFS, ≤−1 dBTP | Task 10; FFmpeg `ebur128` assertions |
| Canvas quadrilateral, smooth 9:16 crop, manual ROI, loss fallback | Tasks 5 and 11; synthetic ROI and crop-velocity tests |
| Low-saliency `@kem12032024` watermark at 30% | Tasks 11–12 and 15; placement/UI/filtergraph tests |
| H.264/AAC 1080×1920/30/yuv420p, silent AAC, fast-start | Task 12; real encode + ffprobe + PTS integration test |
| Atomic outputs, manifest, readable warnings/errors | Tasks 2, 10, 12, 13; failure and redaction tests |
| Checkpoint/resume after Force Quit; cancel preserves valid work | Task 13; crash injection after analysis and TikTok output |
| 80% inactivity removal and 90% detail retention | Task 16; duration-overlap quality report and private E2E |
| First output ≤15 min, full pack ≤20 min, preview correction ≤5 min | Task 16 private supervised benchmark on the acceptance Mac |
| Local privacy, no telemetry/network, music/dependency license handling | Tasks 13, 14, 17; redacted logs, no network code, release license blocker |
| Unsigned runnable macOS app and operator handoff | Task 17; PyInstaller build and headless app smoke test |
| Retention >65% remains a post-publishing KPI, not renderer guarantee | Task 16 benchmarking documentation; absent from technical pass/fail gates |

## Final implementation verification checklist

Run from a clean checkout on the acceptance Mac:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,deepfilter]'
.venv/bin/pytest -m 'not e2e' -q
.venv/bin/ruff check src tests tools
.venv/bin/mypy src/kem_timelapse
bash scripts/build_macos.sh
git status --short
```

Expected: tests/static checks/build/smoke test pass and Git reports no generated tracked changes. Then run the private acceptance command from Task 17. Save its benchmark JSON/Markdown outside Git unless the owner explicitly chooses to publish redacted results.
