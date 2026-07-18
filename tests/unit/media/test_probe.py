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
