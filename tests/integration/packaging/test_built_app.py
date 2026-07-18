import os
import subprocess
from pathlib import Path

import pytest


def test_built_app_passes_headless_smoke_check() -> None:
    executable = Path("dist/Kem Timelapse Studio.app/Contents/MacOS/Kem Timelapse Studio")
    if not executable.exists():
        pytest.skip("unsigned app bundle has not been built")
    environment = os.environ | {"QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [str(executable), "--smoke-test"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "SMOKE_OK" in result.stdout
