from pathlib import Path

from kem_timelapse.domain.models import MediaInfo
from kem_timelapse.ingest.service import IngestService


class FakeProbe:
    def probe(self, path: Path) -> MediaInfo:
        creation = "2026-01-02T00:00:00Z" if path.name == "b.MOV" else None
        return MediaInfo(
            duration_ms=1_000,
            width=3840,
            height=2160,
            fps_num=30,
            fps_den=1,
            codec="hevc",
            rotation_deg=0,
            has_audio=True,
            creation_time=creation,
        )


def test_ingest_orders_creation_time_then_filename(tmp_path: Path) -> None:
    a = tmp_path / "a.MOV"
    b = tmp_path / "b.MOV"
    a.write_bytes(b"a")
    b.write_bytes(b"b")

    clips = IngestService(FakeProbe()).ingest([a, b])

    assert [clip.path.name for clip in clips] == ["b.MOV", "a.MOV"]
    assert [clip.order for clip in clips] == [0, 1]
