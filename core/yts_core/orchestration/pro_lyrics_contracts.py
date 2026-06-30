from __future__ import annotations

from typing import Any


def structure_contract() -> dict[str, Any]:
    return {
        "section_label_format": {
            "allowed_examples": [
                "Verse 1",
                "Verse 2",
                "Pre-Chorus",
                "Chorus",
                "Chorus 2",
                "Final Chorus",
                "Bridge",
                "Outro",
                "Instrumental",
            ],
            "forbidden_examples": ["Verse1", "PreChorus1", "Chorus1", "Chorus2"],
            "sections_must_be_unique": True,
        },
        "hook_placement": {
            "allowed_shapes": ["string", "array", "object"],
            "allowed_object_keys": [
                "first_appearance",
                "repeat_sections",
                "strategy",
                "reason",
                "notes",
            ],
            "section_references_must_exactly_match_sections": True,
            "repeat_sections_must_be_unique": True,
            "repeat_sections_must_exclude_first_appearance": True,
            "valid_repeat_example": {
                "first_appearance": "Chorus",
                "repeat_sections": ["Chorus 2", "Final Chorus"],
            },
            "invalid_repeat_examples": [
                {
                    "first_appearance": "Chorus",
                    "repeat_sections": ["Chorus"],
                },
                {
                    "first_appearance": "Chorus",
                    "repeat_sections": ["Chorus", "Chorus 2"],
                },
            ],
        },
    }


def style_prompt_contract(music_style_plan: dict[str, Any]) -> dict[str, Any]:
    selected_style = _mapping(music_style_plan.get("selected_style"))
    return {
        "style_prompt_draft_must_avoid_forbidden_positive_terms": True,
        "forbidden_positive_terms": _unique_strings(music_style_plan.get("negative_tags", [])),
        "negative_terms_may_include_forbidden_terms": True,
        "style_prompt_draft_must_copy_selected_template_core": True,
        "selected_style_id": str(music_style_plan.get("selected_style_id") or "").strip(),
        "selected_template_id": str(selected_style.get("template_id") or "").strip(),
    }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unique_strings(value: Any) -> list[str]:
    out: list[str] = []
    for item in value if isinstance(value, list) else []:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out
