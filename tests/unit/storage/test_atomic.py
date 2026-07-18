import json
from pathlib import Path

from kem_timelapse.storage.atomic import atomic_write_json


def test_atomic_write_replaces_json_and_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "project.json"

    atomic_write_json(target, {"revision": 1})
    atomic_write_json(target, {"revision": 2})

    assert json.loads(target.read_text()) == {"revision": 2}
    assert list(tmp_path.glob(".project.json.*.tmp")) == []
