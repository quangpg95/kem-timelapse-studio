from __future__ import annotations

import json
from pathlib import Path

from kem_timelapse.quality.metrics import LabeledRange
from kem_timelapse.quality.report import BenchmarkReport


def load_ranges(path: Path) -> list[LabeledRange]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported labels schema")
    ranges = payload.get("ranges")
    if not isinstance(ranges, list):
        raise ValueError("labels must contain a ranges array")
    return [LabeledRange.model_validate(item) for item in ranges]


def load_decisions(project_dir: Path) -> list[LabeledRange]:
    """Load canonical keep/delete segment decisions from persisted analysis artifacts."""
    source_aliases: dict[str, str] = {}
    sources_path = project_dir / "sources.json"
    if sources_path.is_file():
        sources_payload = json.loads(sources_path.read_text(encoding="utf-8"))
        raw_sources = (
            sources_payload.get("sources", []) if isinstance(sources_payload, dict) else []
        )
        if isinstance(raw_sources, list):
            source_aliases = {
                str(source["id"]): Path(str(source["path"])).stem
                for source in raw_sources
                if isinstance(source, dict) and "id" in source and "path" in source
            }
    decisions: list[LabeledRange] = []
    for path in sorted((project_dir / "analysis").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            raw_segments = payload.get("segments", payload.get("decisions", []))
        else:
            raw_segments = payload
        if not isinstance(raw_segments, list):
            continue
        for segment in raw_segments:
            if not isinstance(segment, dict):
                continue
            if "label" in segment and segment["label"] in {"deleted", "kept"}:
                label = segment["label"]
            elif "keep_default" in segment:
                label = "kept" if bool(segment["keep_default"]) else "deleted"
            else:
                continue
            decisions.append(
                LabeledRange.model_validate(
                    {
                        "source_id": source_aliases.get(
                            str(segment["source_id"]), str(segment["source_id"])
                        ),
                        "start_ms": segment["start_ms"],
                        "end_ms": segment["end_ms"],
                        "label": label,
                    }
                )
            )
    if not decisions:
        raise ValueError("analysis contains no canonical segment decisions")
    return decisions


def report_exit_code(report: BenchmarkReport) -> int:
    return 0 if report.passes else 1


def _markdown(report: BenchmarkReport) -> str:
    status = "PASS" if report.passes else "FAIL"
    output_rows = "\n".join(
        f"| {item.variant} | {item.filename} | {'yes' if item.valid else 'no'} |"
        for item in report.outputs
    )
    return f"""# Kem Timelapse benchmark

Overall: **{status}**

| Gate | Result |
| --- | ---: |
| Inactivity removed | {report.quality.inactivity_removed:.1%} |
| Important detail retained | {report.quality.important_detail_retained:.1%} |
| First output | {report.time_to_first_output_seconds:.1f} s |
| Full Content Pack | {report.full_pack_seconds:.1f} s |

| Variant | File | Valid |
| --- | --- | --- |
{output_rows}
"""


def write_reports(report: BenchmarkReport, json_path: Path) -> Path:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    markdown_path = json_path.with_suffix(".md")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return markdown_path
