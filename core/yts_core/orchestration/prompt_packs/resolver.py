from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import PromptPack


def resolve_prompt_pack(
    pack_id: str,
    *,
    version: str | None = None,
    root: Path | str | None = None,
) -> PromptPack:
    root_path = Path(root) if root is not None else Path(__file__).resolve().parent
    pack_dir = root_path / pack_id
    resolved_version = _active_version(pack_dir) if version is None else _non_empty(version, "version")
    release_dir = pack_dir / "releases" / resolved_version
    manifest = _load_json_object(release_dir / "manifest.json")

    manifest_pack_id = _manifest_string(manifest, "pack_id")
    manifest_version = _manifest_string(manifest, "version")
    contract_version = _manifest_string(manifest, "contract_version")
    status = _manifest_string(manifest, "status")
    if manifest_pack_id != pack_id:
        raise ValueError(f"prompt pack manifest pack_id mismatch: {manifest_pack_id} != {pack_id}")
    if manifest_version != resolved_version:
        raise ValueError(
            f"prompt pack manifest version mismatch: {manifest_version} != {resolved_version}"
        )
    if status != "published":
        raise ValueError(f"prompt pack {pack_id}@{resolved_version} is not published")

    system_entry = _manifest_mapping(manifest, "system")
    system_template = _read_template(release_dir, system_entry, f"{pack_id}.system")

    stages_entry = _manifest_mapping(manifest, "stages")
    stage_templates: dict[str, str] = {}
    stage_system_templates: dict[str, str] = {}
    for stage, entry in stages_entry.items():
        if not isinstance(stage, str) or not stage.strip():
            raise ValueError("prompt pack stage names must be non-empty strings")
        if not isinstance(entry, Mapping):
            raise ValueError(f"prompt pack stage {stage} manifest entry must be an object")
        stage_templates[stage] = _read_template(release_dir, entry, f"{pack_id}.{stage}")
        if "system_template" in entry or "system_sha256" in entry:
            stage_system_templates[stage] = _read_stage_system_template(
                release_dir,
                entry,
                f"{pack_id}.{stage}.system",
            )

    return PromptPack(
        pack_id=pack_id,
        version=resolved_version,
        contract_version=contract_version,
        sha256=_pack_sha256(
            pack_id=pack_id,
            version=resolved_version,
            contract_version=contract_version,
            system_entry=system_entry,
            stages_entry=stages_entry,
        ),
        system_template=system_template,
        stage_system_templates=stage_system_templates,
        stage_templates=stage_templates,
    )


def _active_version(pack_dir: Path) -> str:
    active = _load_json_object(pack_dir / "active.json")
    return _manifest_string(active, "version")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"prompt pack file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"prompt pack file must be valid JSON: {path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"prompt pack JSON root must be an object: {path}")
    return parsed


def _read_template(release_dir: Path, entry: Mapping[str, Any], label: str) -> str:
    template_name = _entry_string(entry, "template", label)
    expected_sha256 = _entry_string(entry, "sha256", label)
    path = release_dir / template_name
    text = path.read_text(encoding="utf-8")
    actual_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"prompt pack hash mismatch for {label}: {actual_sha256} != {expected_sha256}"
        )
    if not text.strip():
        raise ValueError(f"prompt pack template must not be empty: {label}")
    return text


def _read_stage_system_template(release_dir: Path, entry: Mapping[str, Any], label: str) -> str:
    template_name = _entry_string(entry, "system_template", label)
    expected_sha256 = _entry_string(entry, "system_sha256", label)
    path = release_dir / template_name
    text = path.read_text(encoding="utf-8")
    actual_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"prompt pack hash mismatch for {label}: {actual_sha256} != {expected_sha256}"
        )
    if not text.strip():
        raise ValueError(f"prompt pack template must not be empty: {label}")
    return text


def _pack_sha256(
    *,
    pack_id: str,
    version: str,
    contract_version: str,
    system_entry: Mapping[str, Any],
    stages_entry: Mapping[str, Any],
) -> str:
    fingerprint = {
        "contract_version": contract_version,
        "pack_id": pack_id,
        "stages": stages_entry,
        "system": system_entry,
        "version": version,
    }
    encoded = json.dumps(
        fingerprint,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _manifest_mapping(manifest: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = manifest.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"prompt pack manifest.{key} must be an object")
    return value


def _manifest_string(manifest: Mapping[str, Any], key: str) -> str:
    return _non_empty(manifest.get(key), f"manifest.{key}")


def _entry_string(entry: Mapping[str, Any], key: str, label: str) -> str:
    return _non_empty(entry.get(key), f"{label}.{key}")


def _non_empty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"prompt pack {label} must be a non-empty string")
    return value.strip()
