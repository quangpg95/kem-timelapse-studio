from __future__ import annotations

import json
from pathlib import Path

from kem_timelapse.quality.benchmark import (
    load_decisions,
    load_ranges,
    report_exit_code,
    write_reports,
)
from kem_timelapse.quality.report import (
    BenchmarkEnvironment,
    BenchmarkOutput,
    BenchmarkReport,
    BenchmarkSource,
    QualityReport,
)


def _passing_report() -> BenchmarkReport:
    return BenchmarkReport(
        app_version="0.1.0",
        ffmpeg_version="ffmpeg 7",
        sources=[
            BenchmarkSource(
                filename="painting.mov",
                codec="hevc",
                duration_ms=3_600_000,
                size_bytes=100,
                unchanged=True,
            )
        ],
        environment=BenchmarkEnvironment(
            platform="macOS",
            machine="arm64",
            free_disk_bytes=10_000,
            volume_type="apfs",
            power_source="ac",
            thermal_state="not_available",
        ),
        stage_seconds={"analysis": 1.0, "render": 2.0},
        outputs=[
            BenchmarkOutput(
                variant=variant,
                filename=f"painting_{variant}.mp4",
                valid=True,
                probe={"video_codec": "h264", "audio_codec": "aac"},
            )
            for variant in ("tiktok-fast", "reels-aesthetic", "shorts-asmr")
        ],
        warning_codes=[],
        quality=QualityReport(
            inactivity_removed=0.80,
            important_detail_retained=0.90,
            inactivity_removed_ms=8_000,
            inactivity_labeled_ms=10_000,
            important_detail_retained_ms=9_000,
            important_detail_labeled_ms=10_000,
            passes_quality_gate=True,
        ),
        time_to_first_output_seconds=500.0,
        full_pack_seconds=1_000.0,
        passes_output_gate=True,
        passes_time_gate=True,
    )


def test_golden_labels_load_as_valid_ranges() -> None:
    path = Path("tests/fixtures/golden/labels.json")

    ranges = load_ranges(path)

    assert sum(item.end_ms - item.start_ms for item in ranges if item.label == "inactive") == 20_000
    assert sum(
        item.end_ms - item.start_ms
        for item in ranges
        if item.label == "important_detail"
    ) == 15_000


def test_benchmark_report_writes_versioned_json_and_markdown(tmp_path: Path) -> None:
    report = _passing_report()
    json_path = tmp_path / "acceptance.json"

    markdown_path = write_reports(report, json_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["sources"][0]["filename"] == "painting.mov"
    assert "/Users/" not in json_path.read_text(encoding="utf-8")
    assert markdown_path == tmp_path / "acceptance.md"
    assert "PASS" in markdown_path.read_text(encoding="utf-8")
    assert report_exit_code(report) == 0


def test_any_failed_gate_returns_nonzero() -> None:
    report = _passing_report().model_copy(update={"passes_time_gate": False})

    assert report_exit_code(report) == 1


def test_analysis_segments_become_duration_decisions(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "clip.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "source_id": "clip-1",
                        "start_ms": 0,
                        "end_ms": 1_000,
                        "keep_default": False,
                    },
                    {
                        "source_id": "clip-1",
                        "start_ms": 1_000,
                        "end_ms": 2_000,
                        "keep_default": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    decisions = load_decisions(tmp_path)

    assert [item.label for item in decisions] == ["deleted", "kept"]


def test_decisions_use_filename_stem_to_match_portable_labels(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    (tmp_path / "sources.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {"id": "clip-fingerprint", "path": "/private/painting-60s.mp4"}
                ],
            }
        ),
        encoding="utf-8",
    )
    (analysis_dir / "clip.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "source_id": "clip-fingerprint",
                        "start_ms": 0,
                        "end_ms": 1_000,
                        "keep_default": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    decisions = load_decisions(tmp_path)

    assert decisions[0].source_id == "painting-60s"
