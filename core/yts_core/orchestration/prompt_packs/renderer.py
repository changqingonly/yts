from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .models import PromptPack
from .resolver import resolve_prompt_pack


def system_prompt(prompt_pack: PromptPack | Mapping[str, str], stage: str | None = None) -> str:
    pack = _coerce_prompt_pack(prompt_pack)
    if stage is not None and stage in pack.stage_system_templates:
        return f"{pack.system_template.rstrip()}\n\n{pack.stage_system_templates[stage].strip()}"
    return pack.system_template


def render_prompt(
    prompt_pack: PromptPack | Mapping[str, str],
    stage: str,
    payload: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> str:
    pack = _coerce_prompt_pack(prompt_pack)
    if stage not in pack.stage_templates:
        raise ValueError(
            f"prompt pack {pack.pack_id}@{pack.version} has no stage template: {stage}"
        )
    return (
        f"YTS_PRO_STAGE: {stage}\n"
        f"{pack.stage_templates[stage]}\n\n"
        "Return JSON object matching this shape:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def _coerce_prompt_pack(prompt_pack: PromptPack | Mapping[str, str]) -> PromptPack:
    if isinstance(prompt_pack, PromptPack):
        return prompt_pack
    if not isinstance(prompt_pack, Mapping):
        raise TypeError("prompt_pack must be a PromptPack or mapping")
    pack_id = _state_string(prompt_pack, "pack_id")
    version = _state_string(prompt_pack, "version")
    expected_sha256 = _state_string(prompt_pack, "sha256")
    resolved = resolve_prompt_pack(pack_id, version=version)
    if resolved.sha256 != expected_sha256:
        raise ValueError(
            f"prompt pack hash mismatch for {pack_id}@{version}: "
            f"{resolved.sha256} != {expected_sha256}"
        )
    return resolved


def _state_string(state: Mapping[str, str], key: str) -> str:
    return _non_empty(state.get(key), f"prompt_pack.{key}")


def _non_empty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"prompt pack {label} must be a non-empty string")
    return value.strip()
