from pathlib import Path

import pytest

from kem_timelapse.domain.errors import ErrorCode, PipelineError
from kem_timelapse.ingest.preflight import Preflight


def test_preflight_reports_required_and_available_disk(tmp_path: Path) -> None:
    check = Preflight(
        binary_lookup=lambda name: f"/usr/local/bin/{name}",
        free_bytes=lambda path: 99,
    )

    with pytest.raises(PipelineError) as caught:
        check.check(tmp_path, estimated_bytes=100)

    assert caught.value.code is ErrorCode.INSUFFICIENT_DISK
    assert caught.value.context == {"required_bytes": 100, "available_bytes": 99}
