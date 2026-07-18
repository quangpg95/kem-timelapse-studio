from pathlib import Path

import pytest

from kem_timelapse.audio.backends import FfmpegDenoiseBackend
from kem_timelapse.media.process import CompletedCommand


class RecordingRunner:
    def __init__(self, *, create_output: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.create_output = create_output

    def run(self, args: list[str], cancel_event: object | None = None) -> CompletedCommand:
        self.calls.append(args)
        if self.create_output:
            Path(args[-1]).write_bytes(b"clean")
        return CompletedCommand(0, "", "")


def test_ffmpeg_fallback_uses_asmr_chain_and_rejects_missing_output(tmp_path: Path) -> None:
    source = tmp_path / "input.wav"
    source.write_bytes(b"wav")
    runner = RecordingRunner()
    output = tmp_path / "output.wav"

    FfmpegDenoiseBackend(runner).process(source, output)

    assert runner.calls == [[
        "ffmpeg", "-y", "-v", "error", "-i", str(source),
        "-af", "highpass=f=80,afftdn=nf=-25,equalizer=f=3000:t=q:w=1:g=2,"
        "equalizer=f=8000:t=q:w=1:g=1,acompressor=threshold=-18dB:ratio=3:"
        "attack=10:release=120,alimiter=limit=0.891",
        str(output),
    ]]

    with pytest.raises(RuntimeError, match="did not create"):
        FfmpegDenoiseBackend(RecordingRunner(create_output=False)).process(
            source, tmp_path / "missing.wav"
        )
