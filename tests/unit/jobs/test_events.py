import json
from pathlib import Path

from kem_timelapse.domain.errors import ErrorCode
from kem_timelapse.jobs.events import JobEvent, JsonlEventSink


def test_jsonl_sink_recursively_redacts_paths_but_keeps_traceback(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "jobs.jsonl"
    sink = JsonlEventSink(log_path)

    sink.emit(
        JobEvent(
            project_id="project-1",
            stage="Analyzing",
            event="failed",
            progress=0.5,
            error_code=ErrorCode.SOURCE_UNAVAILABLE,
            details={
                "source_path": "/Users/me/private.mov",
                "traceback": "Traceback: decoder failed",
                "nested": [{"path": "/private/cache.mov", "reason": "decode"}],
            },
        )
    )

    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["details"]["source_path"] == "<redacted>"
    assert payload["details"]["nested"][0]["path"] == "<redacted>"
    assert payload["details"]["traceback"] == "Traceback: decoder failed"
    assert payload["error_code"] == "SourceUnavailable"
    assert payload["timestamp"].endswith("Z")
