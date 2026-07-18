from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from kem_timelapse.domain.models import SourceClip
from kem_timelapse.media.probe import MediaProbe
from kem_timelapse.media.process import CommandRunner
from kem_timelapse.media.proxy import ProxyBuilder
from kem_timelapse.storage.fingerprint import fingerprint_source


def has_videotoolbox_encoder(name: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and name in result.stdout


@pytest.mark.media
def test_proxy_preserves_duration_and_removes_audio(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe are required for the media proxy test")
    if not has_videotoolbox_encoder("h264_videotoolbox") or not has_videotoolbox_encoder(
        "hevc_videotoolbox"
    ):
        pytest.skip("VideoToolbox H.264 and HEVC encoders are required for the media proxy test")

    source = tmp_path / "source.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=3840x2160:r=30:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=48000:duration=2",
            "-c:v",
            "hevc_videotoolbox",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    probe = MediaProbe(CommandRunner())
    source_info = probe.probe(source)
    clip = SourceClip(
        id="clip-source",
        path=source,
        size_bytes=source.stat().st_size,
        mtime_ns=source.stat().st_mtime_ns,
        fingerprint=fingerprint_source(source),
        media=source_info,
        order=0,
    )

    artifact = ProxyBuilder(CommandRunner()).build(clip, tmp_path / "cache", None)
    proxy_info = probe.probe(artifact.path)

    assert (proxy_info.width, proxy_info.height) == (1280, 720)
    assert abs(proxy_info.fps_num / proxy_info.fps_den - 10) < 0.01
    assert abs(proxy_info.duration_ms - 2_000) <= 100
    assert proxy_info.has_audio is False
