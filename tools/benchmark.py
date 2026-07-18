#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Protocol

from kem_timelapse.cli import _runner_for_project
from kem_timelapse.domain.models import Variant
from kem_timelapse.jobs.runner import JobRunner
from kem_timelapse.media.probe import MediaProbe
from kem_timelapse.media.process import CommandRunner
from kem_timelapse.quality.benchmark import (
    load_decisions,
    load_ranges,
    report_exit_code,
    write_reports,
)
from kem_timelapse.quality.metrics import compute_quality
from kem_timelapse.quality.report import (
    BenchmarkEnvironment,
    BenchmarkOutput,
    BenchmarkReport,
    BenchmarkSource,
)
from kem_timelapse.render.validator import OutputValidator
from kem_timelapse.storage.fingerprint import fingerprint_source
from kem_timelapse.storage.project_repository import ProjectRepository

RunnerFactory = Callable[[Path, Sequence[Path], bool], JobRunner]


class BenchmarkRunner(Protocol):
    def analyze_to_review(self) -> None: ...

    def render_pack(self) -> None: ...


def _command_line(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return "not_available"
    return next(
        (line.strip() for line in result.stdout.splitlines() if line.strip()),
        "not_available",
    )


def _ffmpeg_version() -> str:
    line = _command_line(["ffmpeg", "-version"])
    return " ".join(line.split()[:3]) if line != "not_available" else line


def _app_version() -> str:
    try:
        return version("kem-timelapse")
    except PackageNotFoundError:
        return "0.1.0"


def _volume_type(path: Path) -> str:
    if platform.system() != "Darwin" or shutil.which("diskutil") is None:
        return "not_available"
    result = subprocess.run(
        ["diskutil", "info", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return "not_available"
    for line in result.stdout.splitlines():
        if "File System Personality:" in line:
            return line.split(":", 1)[1].strip().lower().replace(" ", "_")
    return "not_available"


def _power_source() -> str:
    if platform.system() != "Darwin" or shutil.which("pmset") is None:
        return "not_available"
    line = _command_line(["pmset", "-g", "batt"]).lower()
    if "ac power" in line:
        return "ac"
    if "battery power" in line:
        return "battery"
    return "not_available"


def _environment(project_dir: Path) -> BenchmarkEnvironment:
    anchor = project_dir if project_dir.exists() else project_dir.parent
    return BenchmarkEnvironment(
        platform=platform.system() or "not_available",
        machine=platform.machine() or "not_available",
        free_disk_bytes=shutil.disk_usage(anchor).free,
        volume_type=_volume_type(anchor),
        power_source=_power_source(),
        # macOS does not expose a stable, unprivileged thermal-state API on every release.
        thermal_state="not_available",
    )


def _snapshot(path: Path) -> tuple[int, int, str]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, fingerprint_source(path)


def _source_reports(
    sources: Sequence[Path],
    before: dict[Path, tuple[int, int, str]],
) -> list[BenchmarkSource]:
    probe = MediaProbe(CommandRunner())
    reports: list[BenchmarkSource] = []
    for path in sources:
        media = probe.probe(path)
        reports.append(
            BenchmarkSource(
                filename=path.name,
                codec=media.codec,
                duration_ms=media.duration_ms,
                size_bytes=path.stat().st_size,
                unchanged=_snapshot(path) == before[path],
            )
        )
    return reports


def _manifest_outputs(project_dir: Path) -> tuple[list[BenchmarkOutput], list[str]]:
    manifest_path = project_dir / "outputs" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_outputs = manifest.get("outputs", []) if isinstance(manifest, dict) else []
    validator = OutputValidator()
    outputs: list[BenchmarkOutput] = []
    warnings: list[str] = []
    for item in raw_outputs:
        if not isinstance(item, dict):
            continue
        filename = Path(str(item.get("filename", ""))).name
        variant = str(item.get("variant", "unknown"))
        try:
            validated = validator.validate(project_dir / "outputs" / filename)
            probe = validated.model_dump(mode="json", exclude={"path"})
            valid = True
        except Exception as error:
            probe = {"validation_error": type(error).__name__}
            valid = False
        item_warnings = item.get("warning_codes", [])
        if isinstance(item_warnings, list):
            warnings.extend(str(value) for value in item_warnings)
        outputs.append(
            BenchmarkOutput(
                variant=variant,
                filename=filename,
                valid=valid,
                probe=probe,
            )
        )
    return outputs, sorted(set(warnings))


def _create_runner(project_dir: Path, sources: Sequence[Path], overwrite: bool) -> JobRunner:
    return _runner_for_project(project_dir, sources, overwrite)


def run_benchmark(
    sources: Sequence[Path],
    labels_path: Path,
    project_dir: Path,
    *,
    runner_factory: RunnerFactory = _create_runner,
) -> BenchmarkReport:
    resolved_sources = [path.expanduser().resolve(strict=True) for path in sources]
    if not resolved_sources:
        raise ValueError("at least one --source is required")
    labels = load_ranges(labels_path)
    snapshots = {path: _snapshot(path) for path in resolved_sources}
    started = time.monotonic()
    runner = runner_factory(project_dir, resolved_sources, False)
    analysis_started = time.monotonic()
    runner.analyze_to_review()
    analysis_seconds = time.monotonic() - analysis_started
    render_started = time.monotonic()
    runner.render_pack()
    render_seconds = time.monotonic() - render_started
    finished = time.monotonic()

    output_paths = list((project_dir / "outputs").glob("*.mp4"))
    first_output_seconds = min(
        (
            max(0.0, path.stat().st_mtime - time.time() + (finished - started))
            for path in output_paths
        ),
        default=finished - started,
    )
    full_pack_seconds = finished - started
    quality = compute_quality(labels, load_decisions(project_dir))
    outputs, manifest_warnings = _manifest_outputs(project_dir)
    state = ProjectRepository(project_dir).load_state()
    expected_variants = {variant.value for variant in Variant}
    valid_variants = {output.variant for output in outputs if output.valid}
    output_gate = valid_variants == expected_variants
    time_gate = first_output_seconds <= 900.0 and full_pack_seconds <= 1_200.0
    return BenchmarkReport(
        app_version=_app_version(),
        ffmpeg_version=_ffmpeg_version(),
        sources=_source_reports(resolved_sources, snapshots),
        environment=_environment(project_dir),
        stage_seconds={
            "analysis": round(analysis_seconds, 3),
            "render": round(render_seconds, 3),
        },
        outputs=outputs,
        warning_codes=sorted(set([*state.warning_codes, *manifest_warnings])),
        quality=quality,
        time_to_first_output_seconds=round(first_output_seconds, 3),
        full_pack_seconds=round(full_pack_seconds, 3),
        passes_output_gate=output_gate,
        passes_time_gate=time_gate,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full-recording acceptance benchmark.")
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run_benchmark(args.source, args.labels, args.project_dir)
    markdown_path = write_reports(report, args.report)
    print(f"JSON report: {args.report.name}")
    print(f"Markdown report: {markdown_path.name}")
    return report_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
