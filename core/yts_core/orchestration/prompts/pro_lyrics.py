from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..pro_lyrics_contracts import structure_contract, style_prompt_contract
from ..prompt_packs import render_prompt, resolve_prompt_pack, system_prompt

PRO_STAGE_OUTPUT_SCHEMAS: dict[str, Mapping[str, Any]] = {
    "parse_intent": {
        "raw_query": "string",
        "retrieval_query": "string",
        "positive_terms": ["string"],
        "retrieval_tokens": ["string"],
        "scene_cues": ["string"],
        "emotion_cues": ["string"],
        "style_cues": ["string"],
        "negative_terms": ["string"],
        "negative_categories": ["string"],
    },
    "build_song_brief": {
        "core_story": "string",
        "narrative_perspective": "string",
        "target_form": "string",
        "emotion_arc": ["string"],
        "duet_allowed": False,
        "required_devices": ["string"],
        "forbidden_devices": ["string"],
    },
    "plan_music_style": {
        "style_candidates": [
            {
                "id": "string",
                "template_id": "string",
                "label": "string",
                "suno_tags": ["Genre", "subgenre", "vocal tone"],
                "bpm_range": {"min": 80, "max": 96},
                "groove": "string",
                "vocal_profile": "string",
                "instrumentation": ["string"],
                "production_notes": ["string"],
                "fit_score": 4.5,
                "fit_reason": "string",
                "risk": "string",
            }
        ],
        "selected_style_id": "string",
        "selection_reason": "string",
        "negative_tags": ["string"],
    },
    "hook_lab": {
        "candidates": [{"hook": "string", "score": 4.5, "reason": "string"}],
        "selected_hook": "string",
        "hook_strategy": "string",
    },
    "draft_structure_blueprints": {
        "blueprints": [
            {
                "id": "string",
                "mode": "string",
                "sections": ["Verse 1", "Chorus"],
                "section_roles": {"Verse 1": "string"},
                "line_budget": {"Verse 1": 4},
                "energy_curve": {"Verse 1": 1, "Chorus": 4},
                "hook_placement": {
                    "first_appearance": "Chorus",
                    "repeat_sections": ["Final Chorus"],
                    "strategy": "string",
                },
                "vocal_plan": {"mode": "solo"},
                "risk": "string",
            }
        ]
    },
    "critique_structure": {
        "selected_blueprint_id": "string",
        "selected_blueprint": {},
        "critic_notes": ["string"],
        "rejected": [{"id": "string", "reason": "string"}],
    },
    "plan_style_prompt": {
        "style_family": {"id": "string", "label": "string", "template_id": "string"},
        "style_prompt_draft": "Genre, BPM, vocal profile, instruments, production",
        "style_components": ["string"],
        "lyric_guidance": {
            "language": "Chinese",
            "required_sections": ["Verse 1", "Chorus"],
            "hook_policy": "string",
            "mood_arc": "string",
            "line_length_hint": "string",
        },
        "negative_terms": ["string"],
        "source_signals": ["string"],
    },
    "generate_lyrics": {
        "structure_mode": "string",
        "structure": ["Verse 1", "Chorus"],
        "title": "string",
        "style_prompt": "string",
        "lyric_prompt": "[Verse 1]\\n...",
        "hook": "string",
        "clip_suggestion": {
            "start_section": "Chorus",
            "duration_seconds": 15,
            "reason": "string",
        },
        "used_card_ids": ["string"],
        "constraint_check": {
            "negative_constraints_avoided": True,
            "has_repeated_hook": True,
            "has_complete_song_structure": True,
            "has_complete_emotion_arc": True,
            "has_concrete_imagery": True,
            "suno_ready": True,
        },
    },
    "review_quality": {
        "decision": "pass",
        "bucket": "pass_candidate",
        "submit_suno": True,
        "safety": 1,
        "overall_score": 4.0,
        "scores": {
            "hook_match": 5,
            "structure_match": 5,
            "constraint_safety": 5,
            "emotion_arc": 4,
            "singability": 4,
            "suno_format": 5,
        },
        "violations": [],
        "repair_targets": [],
        "main_issues": [],
        "suggestions": [],
        "rationale": "string",
    },
    "repair_lyrics": {
        "structure_mode": "string",
        "structure": ["Verse 1", "Chorus"],
        "title": "string",
        "style_prompt": "string",
        "lyric_prompt": "[Verse 1]\\n...",
        "hook": "string",
        "clip_suggestion": {
            "start_section": "Chorus",
            "duration_seconds": 15,
            "reason": "string",
        },
        "used_card_ids": ["string"],
        "constraint_check": {"suno_ready": True},
    },
    "refine_title": {
        "original_title": "string",
        "final_title": "string",
        "title_candidates": [
            {"title": "string", "kind": "hook_story", "reason": "string", "selected": True}
        ],
        "selection_reason": "string",
    },
}


def pro_lyrics_system_prompt(prompt_pack: Mapping[str, str], stage: str) -> str:
    return system_prompt(prompt_pack, stage)


def stage_output_schema(stage: str) -> Mapping[str, Any]:
    schema = PRO_STAGE_OUTPUT_SCHEMAS.get(stage)
    if schema is None:
        raise ValueError(f"missing pro lyrics output schema for stage: {stage}")
    return schema


def _prompt(
    stage: str,
    payload: dict[str, Any],
    schema: Mapping[str, Any],
    *,
    prompt_pack: Mapping[str, str] | None = None,
) -> str:
    resolved_pack = resolve_prompt_pack("pro_lyrics") if prompt_pack is None else prompt_pack
    return render_prompt(resolved_pack, stage, payload, schema)


def _parse_intent_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _song_brief_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _music_style_plan_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _hook_lab_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _structure_blueprints_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    payload = dict(payload)
    payload.setdefault("structure_contract", structure_contract())
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _structure_critique_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _style_prompt_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    payload = dict(payload)
    music_style_plan = payload.get("music_style_plan")
    contract_source = music_style_plan if isinstance(music_style_plan, dict) else {}
    payload.setdefault("style_prompt_contract", style_prompt_contract(contract_source))
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _generate_lyrics_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _quality_review_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _repair_lyrics_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )


def _title_refinement_prompt(
    stage: str, payload: dict[str, Any], *, prompt_pack: Mapping[str, str] | None = None
) -> str:
    return _prompt(
        stage,
        payload,
        stage_output_schema(stage),
        prompt_pack=prompt_pack,
    )
