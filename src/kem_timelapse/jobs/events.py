from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from kem_timelapse.domain.errors import ErrorCode, WarningCode
from kem_timelapse.domain.models import Variant

_REDACTED_KEYS = frozenset({"path", "source_path", "music_path"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobEvent(BaseModel):
    timestamp: datetime = Field(default_factory=_utc_now)
    project_id: str
    stage: str
    event: str
    clip_id: str | None = None
    variant: Variant | None = None
    progress: float = Field(ge=0.0, le=1.0)
    warning_code: WarningCode | None = None
    error_code: ErrorCode | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if str(key) in _REDACTED_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


class JsonlEventSink:
    """Append durable, privacy-redacted structured events to a local JSONL file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def emit(self, event: JobEvent) -> None:
        payload = _redact(event.model_dump(mode="json", exclude_none=True))
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
