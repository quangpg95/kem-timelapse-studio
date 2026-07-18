import json
from pathlib import Path

from kem_timelapse.domain.errors import WarningCode
from kem_timelapse.domain.models import Variant
from kem_timelapse.render.manifest import sha256_file, write_manifest
from kem_timelapse.render.models import ManifestEntry, OutputProbe


def entry(path: Path, variant: Variant = Variant.TIKTOK_FAST) -> ManifestEntry:
    return ManifestEntry(
        variant=variant,
        filename=path.name,
        sha256=sha256_file(path),
        timeline_revision=3,
        elapsed_seconds=1.25,
        probe=OutputProbe(
            path=path,
            video_codec="h264",
            width=1080,
            height=1920,
            pixel_format="yuv420p",
            fps=30,
            audio_codec="aac",
            has_aac=True,
            start_time_ms=0,
            duration_ms=30_000,
        ),
        warning_codes=[WarningCode.AUDIO_DENOISE_DEGRADED],
        source_fingerprints={"clip-1": "fingerprint-1"},
        analyzer_version="heuristic-v1",
        composer_version="composer-v1",
        audio_preset_version="audio-v1",
    )


def test_manifest_is_atomic_redacted_and_updates_by_variant(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    first = outputs / "first.mp4"
    second = outputs / "second.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    write_manifest(tmp_path, entry(first))
    write_manifest(tmp_path, entry(second, Variant.REELS_AESTHETIC))

    path = outputs / "manifest.json"
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 1
    assert payload["sources"] == [{"id": "clip-1", "fingerprint": "fingerprint-1"}]
    assert [item["variant"] for item in payload["outputs"]] == [
        "tiktok-fast",
        "reels-aesthetic",
    ]
    assert payload["outputs"][0]["probe"]["path"] == "first.mp4"
    assert str(tmp_path) not in path.read_text()
    assert not list(outputs.glob("*.tmp"))
