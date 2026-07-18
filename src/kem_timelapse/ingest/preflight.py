from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from kem_timelapse.domain.errors import ErrorCode, PipelineError


class Preflight:
    def __init__(
        self,
        binary_lookup: Callable[[str], str | None] = shutil.which,
        free_bytes: Callable[[Path], int] | None = None,
    ) -> None:
        self._binary_lookup = binary_lookup
        self._free_bytes = free_bytes or (lambda path: shutil.disk_usage(path).free)

    def check(self, project_root: Path, estimated_bytes: int) -> None:
        for binary in ("ffmpeg", "ffprobe"):
            if self._binary_lookup(binary) is None:
                raise PipelineError(
                    ErrorCode.RENDER_BACKEND_UNAVAILABLE,
                    f"Required binary is unavailable: {binary}",
                    context={"binary": binary},
                )
        if not os.access(project_root, os.W_OK):
            raise PipelineError(
                ErrorCode.OUTPUT_NOT_WRITABLE,
                "Project output directory is not writable",
                context={"path": str(project_root)},
            )
        available_bytes = self._free_bytes(project_root)
        if available_bytes < estimated_bytes:
            raise PipelineError(
                ErrorCode.INSUFFICIENT_DISK,
                "Insufficient disk space for project output",
                context={"required_bytes": estimated_bytes, "available_bytes": available_bytes},
            )
