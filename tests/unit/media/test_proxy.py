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
            duration_ms=10_000,
            width=3840,
            height=2160,
            fps_num=30,
            fps_den=1,
            codec="hevc",
            rotation_deg=0,
            has_audio=True,
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
