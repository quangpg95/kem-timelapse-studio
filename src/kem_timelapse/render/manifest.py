from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from kem_timelapse.domain.models import Variant
from kem_timelapse.render.models import ManifestEntry
from kem_timelapse.storage.atomic import atomic_write_json


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _app_version() -> str:
    try:
        return version("kem-timelapse")
    except PackageNotFoundError:
        return "0.1.0"


def _shareable_entry(entry: ManifestEntry) -> dict[str, Any]:
    payload = entry.model_dump(
        mode="json",
        exclude={
            "source_fingerprints",
            "analyzer_version",
            "composer_version",
            "audio_preset_version",
        },
    )
    payload["probe"]["path"] = entry.probe.path.name
    return payload


def write_manifest(project_root: Path, entry: ManifestEntry) -> None:
    """Atomically add or replace one variant in the shareable output manifest."""
    outputs_dir = project_root / "outputs"
    output_path = outputs_dir / entry.filename
    if Path(entry.filename).name != entry.filename:
        raise ValueError("manifest filename must not contain a path")
    if not output_path.is_file():
        raise ValueError("manifest output does not exist")
    actual_digest = sha256_file(output_path)
    if actual_digest != entry.sha256:
        raise ValueError("manifest checksum does not match output")

    manifest_path = outputs_dir / "manifest.json"
    existing: dict[str, Any] = {}
    if manifest_path.is_file():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
            raise ValueError("unsupported manifest schema")
        existing = loaded

    source_map = {
        str(item["id"]): str(item["fingerprint"])
        for item in existing.get("sources", [])
        if isinstance(item, dict) and "id" in item and "fingerprint" in item
    }
    source_map.update(entry.source_fingerprints)
    output_map = {
        str(item["variant"]): item
        for item in existing.get("outputs", [])
        if isinstance(item, dict) and "variant" in item
    }
    output_map[entry.variant.value] = _shareable_entry(entry)
    variant_order = {variant.value: index for index, variant in enumerate(Variant)}
    payload = {
        "schema_version": 1,
        "app_version": _app_version(),
        "sources": [
            {"id": source_id, "fingerprint": fingerprint}
            for source_id, fingerprint in sorted(source_map.items())
        ],
        "analyzer_version": entry.analyzer_version,
        "composer_version": entry.composer_version,
        "audio_preset_version": entry.audio_preset_version,
        "outputs": sorted(
            output_map.values(),
            key=lambda item: variant_order.get(str(item["variant"]), len(variant_order)),
        ),
    }
    atomic_write_json(manifest_path, payload)
