from pathlib import Path

import pytest

from kem_timelapse.media.probe import MediaProbe
from kem_timelapse.media.process import CommandRunner

GENERATED = Path("tests/generated_media")


@pytest.mark.media
def test_generated_media_covers_rotation_and_missing_audio() -> None:
    rotated = GENERATED / "painting-rotation-90.mp4"
    no_audio = GENERATED / "painting-no-audio.mp4"
    if not rotated.is_file() or not no_audio.is_file():
        pytest.skip("generated media not created")

    probe = MediaProbe(CommandRunner())
    rotated_info = probe.probe(rotated)
    silent_info = probe.probe(no_audio)

    assert (rotated_info.width, rotated_info.height) == (3840, 2160)
    assert rotated_info.rotation_deg == 90
    assert silent_info.has_audio is False
