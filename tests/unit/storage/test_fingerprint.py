from pathlib import Path

from kem_timelapse.storage.fingerprint import fingerprint_source


def test_fingerprint_changes_when_tail_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.mov"
    source.write_bytes(b"a" * 64 + b"tail-a")

    before = fingerprint_source(source, chunk_bytes=16)
    source.write_bytes(b"a" * 64 + b"tail-b")
    after = fingerprint_source(source, chunk_bytes=16)

    assert before != after
