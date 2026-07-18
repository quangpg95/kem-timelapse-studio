from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from kem_timelapse import cli
from kem_timelapse.domain.models import Variant
from kem_timelapse.editing.commands import SetWatermark
from kem_timelapse.editing.session import EditingSession
from kem_timelapse.quality.benchmark import load_decisions, load_ranges
from kem_timelapse.quality.metrics import compute_quality
from kem_timelapse.render.validator import OutputValidator
from kem_timelapse.storage.fingerprint import fingerprint_source
from kem_timelapse.storage.project_repository import ProjectRepository


class InjectedRestart(BaseException):
    pass


def _restart_after(expected: str) -> Callable[[str], None]:
    fired = False

    def hook(name: str) -> None:
        nonlocal fired
        if not fired and name == expected:
            fired = True
            raise InjectedRestart(name)

    return hook


def _snapshot(path: Path) -> tuple[int, int, str]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, fingerprint_source(path)


def _packet_endpoints(path: Path, selector: str) -> tuple[float, float]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            selector,
            "-show_packets",
            "-show_entries",
            "packet=pts_time",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-1_000:]
    points = [
        float(item["pts_time"])
        for item in json.loads(result.stdout)["packets"]
        if "pts_time" in item
    ]
    assert points
    return points[0], points[-1]


def _assert_no_black_gap(path: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "info",
            "-i",
            str(path),
            "-vf",
            "blackdetect=d=0.20:pix_th=0.02",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-1_000:]
    assert "black_start:" not in result.stderr


def _target_acceptance_mac() -> bool:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return False
    memory = subprocess.run(
        ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=False
    )
    chip = subprocess.run(
        ["sysctl", "-n", "machdep.cpu.brand_string"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        memory.returncode == 0
        and int(memory.stdout.strip()) >= 24 * 1024**3
        and chip.returncode == 0
        and "M3 Pro" in chip.stdout
    )


@pytest.mark.e2e
def test_private_full_recording_acceptance(tmp_path: Path) -> None:
    source_value = os.environ.get("KEM_TIMELAPSE_ACCEPTANCE_SOURCE")
    labels_value = os.environ.get("KEM_TIMELAPSE_ACCEPTANCE_LABELS")
    if not source_value or not labels_value:
        pytest.skip("private acceptance recording not configured")
    assert platform.system() == "Darwin" and platform.machine() == "arm64", (
        "private acceptance requires macOS Apple Silicon"
    )

    source = Path(source_value).expanduser().resolve(strict=True)
    labels_path = Path(labels_value).expanduser().resolve(strict=True)
    source_before = _snapshot(source)
    project_dir = tmp_path / "acceptance-project"
    started = time.monotonic()

    analysis_runner = cli._runner_for_project(project_dir, [source])
    first_clip_id = analysis_runner._stages.selected_clip_ids()[0]
    analysis_runner._checkpoint_hook = _restart_after(f"analysis:{first_clip_id}")
    with pytest.raises(InjectedRestart):
        analysis_runner.analyze_to_review()
    cli._runner_for_project(project_dir, [source]).analyze_to_review()

    repository = ProjectRepository(project_dir)
    timeline = repository.load_timeline(Variant.TIKTOK_FAST)
    edit_started = time.monotonic()
    edited = EditingSession(timeline).apply(
        SetWatermark(text=timeline.watermark_text, opacity=0.29)
    )
    repository.save_timeline(edited)
    preview_edit_seconds = time.monotonic() - edit_started

    render_runner = cli._runner_for_project(project_dir, overwrite=False)
    render_runner._checkpoint_hook = _restart_after("render:tiktok-fast")
    with pytest.raises(InjectedRestart):
        render_runner.render_pack()
    first_output_seconds = time.monotonic() - started
    cli._runner_for_project(project_dir, overwrite=False).render_pack()
    full_pack_seconds = time.monotonic() - started

    assert _snapshot(source) == source_before
    manifest = json.loads((project_dir / "outputs" / "manifest.json").read_text())
    entries = manifest["outputs"]
    assert {entry["variant"] for entry in entries} == {variant.value for variant in Variant}
    for entry in entries:
        output = project_dir / "outputs" / entry["filename"]
        probe = OutputValidator().validate(output)
        assert (probe.video_codec, probe.audio_codec) == ("h264", "aac")
        assert (probe.width, probe.height, probe.fps) == (1080, 1920, 30.0)
        _assert_no_black_gap(output)
        video_start, video_end = _packet_endpoints(output, "v:0")
        audio_start, audio_end = _packet_endpoints(output, "a:0")
        assert abs(video_start - audio_start) < 0.1
        assert abs(video_end - audio_end) < 0.1

    quality = compute_quality(load_ranges(labels_path), load_decisions(project_dir))
    assert quality.inactivity_removed >= 0.80
    assert quality.important_detail_retained >= 0.90
    assert preview_edit_seconds <= 300.0
    if _target_acceptance_mac():
        assert first_output_seconds <= 900.0
        assert full_pack_seconds <= 1_200.0
