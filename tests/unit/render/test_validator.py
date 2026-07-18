import json
from pathlib import Path

import pytest

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.media.process import CompletedCommand
from kem_timelapse.render.validator import OutputValidator


class FakeProbeRunner:
    def __init__(self, payload: dict[str, object] | None = None, returncode: int = 0) -> None:
        self.payload = payload or valid_payload()
        self.returncode = returncode

    def run(self, args: list[str], cancel_event: object | None = None) -> CompletedCommand:
        return CompletedCommand(self.returncode, json.dumps(self.payload), "probe failed")


def valid_payload() -> dict[str, object]:
    return {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "start_time": "0.000000",
            "duration": "30.0",
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "pix_fmt": "yuv420p",
                "avg_frame_rate": "30/1",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }


def test_validator_accepts_exact_vertical_contract(tmp_path: Path) -> None:
    output = tmp_path / "video.mp4"
    output.write_bytes(b"mp4")

    probe = OutputValidator(FakeProbeRunner()).validate(output)

    assert probe.width == 1080 and probe.height == 1920
    assert probe.fps == 30.0 and probe.has_aac is True
    assert probe.duration_ms == 30_000 and probe.start_time_ms == 0


@pytest.mark.parametrize(
    ("mutation", "violation"),
    [
        (("format", "format_name", "matroska"), "container"),
        (("format", "start_time", "-0.100"), "start_time"),
        (("format", "duration", "0"), "duration"),
        (("video", "codec_name", "hevc"), "video_codec"),
        (("video", "width", 720), "dimensions"),
        (("video", "pix_fmt", "yuv444p"), "pixel_format"),
        (("video", "avg_frame_rate", "30000/1001"), "fps"),
        (("audio", "codec_name", "opus"), "audio_codec"),
    ],
)
def test_validator_rejects_each_contract_violation(
    tmp_path: Path,
    mutation: tuple[str, str, object],
    violation: str,
) -> None:
    payload = valid_payload()
    section, key, value = mutation
    if section == "format":
        payload["format"][key] = value  # type: ignore[index]
    elif section == "video":
        payload["streams"][0][key] = value  # type: ignore[index]
    else:
        payload["streams"][1][key] = value  # type: ignore[index]
    output = tmp_path / "bad.mp4"
    output.write_bytes(b"mp4")

    with pytest.raises(PipelineError) as caught:
        OutputValidator(FakeProbeRunner(payload)).validate(output)

    assert caught.value.code is ErrorCode.OUTPUT_VALIDATION_FAILED
    assert violation in caught.value.context["violations"]
    assert caught.value.context["filename"] == "bad.mp4"
