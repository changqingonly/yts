"""Pro lyrics LangGraph nodes and strict payload validation."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from ...schemas.common import StageTrace
from ..pro_lyrics_contracts import structure_contract, style_prompt_contract
from ..prompts.pro_lyrics import (
    _generate_lyrics_prompt,
    _hook_lab_prompt,
    _music_style_plan_prompt,
    _parse_intent_prompt,
    _quality_review_prompt,
    _repair_lyrics_prompt,
    _song_brief_prompt,
    _structure_blueprints_prompt,
    _structure_critique_prompt,
    _style_prompt_prompt,
    _title_refinement_prompt,
    pro_lyrics_system_prompt,
)
from ..state import CreationState
from ..style_templates import match_style_templates
from ..suno_postprocess import postprocess_suno_generation
from ..validators.pro_lyrics import (
    DECISION_REPAIR,
    _blueprint_items,
    _build_final_draft,
    _normalize_generation_format,
    _normalize_generation_payload,
    _normalize_hook_lab,
    _normalize_intent,
    _normalize_music_style_plan,
    _normalize_quality_review,
    _normalize_song_brief,
    _normalize_style_spec,
    _normalize_title_refinement,
    _require_list,
    _require_mapping,
    _selected_blueprint,
    _skip_title_refinement_for_quality_gate,
    _strip_json_fence,
    _structure_plan_from_blueprint,
    _validate_generation_against_pro_plan,
    _validate_style_spec_matches_music_style,
)


def _append_stage(
    state: CreationState, name: str, provider: str, ok: bool = True
) -> list[StageTrace]:
    stages = list(state.get("stages", []))
    stages.append(StageTrace(name=name, ok=ok, note=provider))
    return stages


def _prompt_pack(state: CreationState) -> dict:
    if "prompt_pack" not in state:
        raise ValueError("prompt_pack is required")
    return _require_mapping(state["prompt_pack"], "prompt_pack")


def _record_llm_call(state: CreationState, stage: str, llm_call: dict[str, Any]) -> dict[str, Any]:
    calls = dict(state.get("llm_calls", {}))
    calls[stage] = llm_call
    return calls


def _generation_context(state: CreationState) -> dict[str, Any]:
    song_brief = _require_mapping(state["song_brief"], "song_brief")
    style_spec = _require_mapping(state["style_spec"], "style_spec")
    music_style_plan = _require_mapping(state["music_style_plan"], "music_style_plan")
    selected_style = _require_mapping(
        music_style_plan.get("selected_style"), "music_style_plan.selected_style"
    )
    hook_lab = _require_mapping(state["hook_lab"], "hook_lab")
    professional_plan = _require_mapping(state["professional_plan"], "professional_plan")
    selected_blueprint = _require_mapping(
        professional_plan.get("selected_blueprint"), "professional_plan.selected_blueprint"
    )
    return {
        "user_prompt": state["user_prompt"],
        "story": {
            "core_story": song_brief["core_story"],
            "narrative_perspective": song_brief["narrative_perspective"],
            "target_form": song_brief["target_form"],
            "emotion_arc": song_brief["emotion_arc"],
        },
        "style": {
            "style_family": style_spec["style_family"],
            "selected_style": {
                "id": selected_style["id"],
                "label": selected_style["label"],
                "template_id": selected_style["template_id"],
                "bpm_range": selected_style["bpm_range"],
                "groove": selected_style["groove"],
                "vocal_profile": selected_style["vocal_profile"],
                "instrumentation": selected_style["instrumentation"],
                "production_notes": selected_style["production_notes"],
            },
            "style_prompt": style_spec["style_prompt_draft"],
            "lyric_guidance": style_spec["lyric_guidance"],
        },
        "hook": {
            "selected_hook": hook_lab["selected_hook"],
            "hook_strategy": hook_lab.get("hook_strategy", ""),
        },
        "structure": {
            "mode": selected_blueprint["mode"],
            "sections": selected_blueprint["sections"],
            "section_roles": selected_blueprint.get("section_roles", {}),
            "line_budget": selected_blueprint.get("line_budget", {}),
            "energy_curve": selected_blueprint.get("energy_curve", {}),
            "hook_placement": selected_blueprint.get("hook_placement", {}),
            "bridge_function": selected_blueprint.get("bridge_function", ""),
        },
        "constraints": {
            "duet_allowed": song_brief["duet_allowed"],
            "required_devices": song_brief["required_devices"],
            "forbidden_devices": song_brief["forbidden_devices"],
            "negative_terms": style_spec["negative_terms"],
            "negative_tags": music_style_plan["negative_tags"],
            "forbidden_meta_tags": _forbidden_meta_tags(selected_blueprint),
        },
    }


def _review_context(state: CreationState) -> dict[str, Any]:
    generation_context = _generation_context(state)
    structure = _require_mapping(generation_context["structure"], "generation_context.structure")
    constraints = _require_mapping(generation_context["constraints"], "generation_context.constraints")
    return {
        "user_prompt": generation_context["user_prompt"],
        "generation": _require_mapping(state["generation"], "generation"),
        "expected": {
            "selected_hook": _require_mapping(generation_context["hook"], "generation_context.hook")[
                "selected_hook"
            ],
            "structure": {
                "mode": structure["mode"],
                "sections": structure["sections"],
                "line_budget": structure["line_budget"],
                "energy_curve": structure["energy_curve"],
                "hook_placement": structure["hook_placement"],
            },
            "constraints": constraints,
            "emotion_arc": _require_mapping(generation_context["story"], "generation_context.story")[
                "emotion_arc"
            ],
            "style_prompt": _require_mapping(generation_context["style"], "generation_context.style")[
                "style_prompt"
            ],
        },
    }


def _forbidden_meta_tags(selected_blueprint: dict[str, Any]) -> list[str]:
    vocal_plan = selected_blueprint.get("vocal_plan")
    if not isinstance(vocal_plan, dict):
        return []
    tags = vocal_plan.get("forbidden_meta_tags")
    if not isinstance(tags, list):
        return []
    return [str(tag).strip() for tag in tags if str(tag).strip()]


class ProLyricsNodes:
    def __init__(self, backend) -> None:
        self.backend = backend

    async def validate_request(self, state: CreationState) -> dict:
        user_prompt = str(state["user_prompt"]).strip()
        if not user_prompt:
            raise ValueError("user_prompt must not be empty")
        return {
            "user_prompt": user_prompt,
            "prompt_pack": _prompt_pack(state),
            "stages": _append_stage(state, "validate_request", "gate"),
        }

    async def parse_intent(self, state: CreationState) -> dict:
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "parse_intent",
            {
                "user_prompt": state["user_prompt"],
                "music_dimensions": state.get("music_dimensions", {}),
            },
            _parse_intent_prompt,
            prompt_pack=_prompt_pack(state),
        )
        intent = _normalize_intent(payload)
        return {
            "intent": intent,
            "llm_calls": _record_llm_call(state, "parse_intent", llm_call),
            "stages": _append_stage(state, "parse_intent", provider),
        }

    async def build_song_brief(self, state: CreationState) -> dict:
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "build_song_brief",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
            },
            _song_brief_prompt,
            prompt_pack=_prompt_pack(state),
        )
        brief = _normalize_song_brief(payload)
        return {
            "song_brief": brief,
            "llm_calls": _record_llm_call(state, "build_song_brief", llm_call),
            "stages": _append_stage(state, "build_song_brief", provider),
        }

    async def plan_music_style(self, state: CreationState) -> dict:
        intent = _require_mapping(state["intent"], "intent")
        song_brief = _require_mapping(state["song_brief"], "song_brief")
        style_template_candidates = match_style_templates(
            user_prompt=state["user_prompt"],
            intent=intent,
            song_brief=song_brief,
        )
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "plan_music_style",
            {
                "user_prompt": state["user_prompt"],
                "intent": intent,
                "song_brief": song_brief,
                "style_template_candidates": style_template_candidates,
            },
            _music_style_plan_prompt,
            prompt_pack=_prompt_pack(state),
        )
        music_style_plan = _normalize_music_style_plan(payload, style_template_candidates)
        return {
            "style_template_candidates": style_template_candidates,
            "music_style_plan": music_style_plan,
            "llm_calls": _record_llm_call(state, "plan_music_style", llm_call),
            "stages": _append_stage(state, "plan_music_style", provider),
        }

    async def hook_lab(self, state: CreationState) -> dict:
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "hook_lab",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
                "song_brief": _require_mapping(state["song_brief"], "song_brief"),
                "music_style_plan": _require_mapping(
                    state["music_style_plan"], "music_style_plan"
                ),
            },
            _hook_lab_prompt,
            prompt_pack=_prompt_pack(state),
        )
        hook = _normalize_hook_lab(payload)
        return {
            "hook_lab": hook,
            "llm_calls": _record_llm_call(state, "hook_lab", llm_call),
            "stages": _append_stage(state, "hook_lab", provider),
        }

    async def draft_structure_blueprints(self, state: CreationState) -> dict:
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "draft_structure_blueprints",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
                "song_brief": _require_mapping(state["song_brief"], "song_brief"),
                "music_style_plan": _require_mapping(
                    state["music_style_plan"], "music_style_plan"
                ),
                "hook_lab": _require_mapping(state["hook_lab"], "hook_lab"),
                "structure_contract": structure_contract(),
            },
            _structure_blueprints_prompt,
            prompt_pack=_prompt_pack(state),
        )
        blueprint_items = _blueprint_items(payload)
        if len(blueprint_items) < 2:
            raise ValueError("pro structure planner requires at least two blueprints")
        return {
            "structure_blueprints": {"blueprints": blueprint_items},
            "llm_calls": _record_llm_call(state, "draft_structure_blueprints", llm_call),
            "stages": _append_stage(state, "draft_structure_blueprints", provider),
        }

    async def critique_structure(self, state: CreationState) -> dict:
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "critique_structure",
            {
                "user_prompt": state["user_prompt"],
                "song_brief": _require_mapping(state["song_brief"], "song_brief"),
                "music_style_plan": _require_mapping(
                    state["music_style_plan"], "music_style_plan"
                ),
                "hook_lab": _require_mapping(state["hook_lab"], "hook_lab"),
                "structure_blueprints": _require_mapping(
                    state["structure_blueprints"], "structure_blueprints"
                ),
            },
            _structure_critique_prompt,
            prompt_pack=_prompt_pack(state),
        )
        blueprints = _require_list(
            _require_mapping(state["structure_blueprints"], "structure_blueprints").get(
                "blueprints"
            ),
            "structure_blueprints.blueprints",
        )
        selected = _selected_blueprint(payload, blueprints)
        selected = _blueprint_items({"blueprints": [selected]})[0]
        structure_plan = _structure_plan_from_blueprint(selected, payload)
        professional_plan = {
            "song_brief": _require_mapping(state["song_brief"], "song_brief"),
            "music_style_plan": _require_mapping(
                state["music_style_plan"], "music_style_plan"
            ),
            "hook_lab": _require_mapping(state["hook_lab"], "hook_lab"),
            "structure_blueprints": blueprints,
            "structure_critique": payload,
            "selected_blueprint": selected,
        }
        return {
            "structure_critique": payload,
            "professional_plan": professional_plan,
            "structure_plan": structure_plan,
            "structure": "\n".join(structure_plan["structure_candidates"][0]["structure"]),
            "llm_calls": _record_llm_call(state, "critique_structure", llm_call),
            "stages": _append_stage(state, "critique_structure", provider),
        }

    async def plan_style_prompt(self, state: CreationState) -> dict:
        music_style_plan = _require_mapping(state["music_style_plan"], "music_style_plan")
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "plan_style_prompt",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
                "music_style_plan": music_style_plan,
                "structure_plan": _require_mapping(state["structure_plan"], "structure_plan"),
                "professional_plan": _require_mapping(
                    state["professional_plan"], "professional_plan"
                ),
                "style_prompt_contract": style_prompt_contract(music_style_plan),
            },
            _style_prompt_prompt,
            prompt_pack=_prompt_pack(state),
        )
        style_spec = _normalize_style_spec(payload)
        _validate_style_spec_matches_music_style(
            style_spec,
            music_style_plan,
        )
        professional_plan = dict(_require_mapping(state["professional_plan"], "professional_plan"))
        professional_plan["style_spec"] = style_spec
        return {
            "style_spec": style_spec,
            "style": style_spec["style_prompt_draft"],
            "professional_plan": professional_plan,
            "llm_calls": _record_llm_call(state, "plan_style_prompt", llm_call),
            "stages": _append_stage(state, "plan_style_prompt", provider),
        }

    async def generate_lyrics(self, state: CreationState) -> dict:
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "generate_lyrics",
            {"generation_context": _generation_context(state)},
            _generate_lyrics_prompt,
            prompt_pack=_prompt_pack(state),
        )
        generation = _normalize_generation_payload(
            payload,
        )
        _validate_generation_against_pro_plan(
            generation, _require_mapping(state["professional_plan"], "professional_plan")
        )
        return {
            "generation": generation,
            "lyrics": generation["lyric_prompt"],
            "style": generation["style_prompt"],
            "title": generation["title"],
            "llm_calls": _record_llm_call(state, "generate_lyrics", llm_call),
            "stages": _append_stage(state, "generate_lyrics", provider),
        }

    async def review_quality(self, state: CreationState) -> dict:
        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "review_quality",
            {"review_context": _review_context(state)},
            _quality_review_prompt,
            prompt_pack=_prompt_pack(state),
        )
        review = _normalize_quality_review(payload)
        return {
            "quality_review": review,
            "llm_calls": _record_llm_call(state, "review_quality", llm_call),
            "stages": _append_stage(state, "review_quality", provider),
        }

    async def repair_lyrics(self, state: CreationState) -> dict:
        review = _require_mapping(state["quality_review"], "quality_review")
        generation = _require_mapping(state["generation"], "generation")
        if review["decision"] != DECISION_REPAIR:
            return {
                "generation": generation,
                "quality_review": review,
                "stages": _append_stage(state, "repair_lyrics", "gate"),
            }

        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "repair_lyrics",
            {
                "user_prompt": state["user_prompt"],
                "generation": generation,
                "quality_review": review,
                "generation_context": _generation_context(state),
            },
            _repair_lyrics_prompt,
            prompt_pack=_prompt_pack(state),
        )
        repaired = _normalize_generation_payload(
            payload,
        )
        _validate_generation_against_pro_plan(
            repaired, _require_mapping(state["professional_plan"], "professional_plan")
        )
        repaired_review = dict(review)
        repaired_review["repair_attempted"] = True
        repaired_review["repair_succeeded"] = True
        return {
            "generation": repaired,
            "quality_review": repaired_review,
            "lyrics": repaired["lyric_prompt"],
            "style": repaired["style_prompt"],
            "title": repaired["title"],
            "llm_calls": _record_llm_call(state, "repair_lyrics", llm_call),
            "stages": _append_stage(state, "repair_lyrics", provider),
        }

    async def normalize_suno_format(self, state: CreationState) -> dict:
        generation = _normalize_generation_format(
            _require_mapping(state["generation"], "generation"),
        )
        generation = postprocess_suno_generation(generation).generation
        return {
            "generation": generation,
            "lyrics": generation["lyric_prompt"],
            "style": generation["style_prompt"],
            "title": generation["title"],
            "stages": _append_stage(state, "normalize_suno_format", "normalizer"),
        }

    async def refine_title(self, state: CreationState) -> dict:
        review = _require_mapping(state["quality_review"], "quality_review")
        generation = _require_mapping(state["generation"], "generation")
        if not review["submit_suno"]:
            title_refinement = _skip_title_refinement_for_quality_gate(generation, review)
            return {
                "title_refinement": title_refinement,
                "title": title_refinement["final_title"],
                "stages": _append_stage(state, "refine_title", "gate"),
            }

        payload, provider, llm_call = await _generate_json_object(
            self.backend,
            "refine_title",
            {
                "user_prompt": state["user_prompt"],
                "generation": generation,
                "quality_review": review,
                "structure_plan": _require_mapping(state["structure_plan"], "structure_plan"),
            },
            _title_refinement_prompt,
            prompt_pack=_prompt_pack(state),
        )
        title_refinement = _normalize_title_refinement(payload, generation)
        return {
            "title_refinement": title_refinement,
            "title": title_refinement["final_title"],
            "llm_calls": _record_llm_call(state, "refine_title", llm_call),
            "stages": _append_stage(state, "refine_title", provider),
        }

    async def build_response(self, state: CreationState) -> dict:
        generation = _require_mapping(state["generation"], "generation")
        title_refinement = _require_mapping(state["title_refinement"], "title_refinement")
        title = str(title_refinement["final_title"]).strip()
        lyrics = str(generation["lyric_prompt"]).strip()
        style = str(generation["style_prompt"]).strip()
        return {
            "title": title,
            "lyrics": lyrics,
            "style": style,
            "final_draft": _build_final_draft(title=title, style=style, lyrics=lyrics),
            "stages": _append_stage(state, "build_response", "assembler"),
        }

async def _generate_json_object(
    backend,
    stage: str,
    payload: dict[str, Any],
    prompt_builder,
    *,
    prompt_pack: dict,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    messages = [
        {
            "role": "system",
            "content": pro_lyrics_system_prompt(prompt_pack, stage),
        },
        {"role": "user", "content": prompt_builder(stage, payload, prompt_pack=prompt_pack)},
    ]
    started_at = perf_counter()
    response = await backend.generate_text(
        messages,
        response_format={"type": "json_object"},
    )
    duration_ms = max(0, int(round((perf_counter() - started_at) * 1000)))
    content = _strip_json_fence(response.text)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{stage} must return a strict JSON object: {_json_decode_message(exc)} "
            f"at line {exc.lineno} column {exc.colno}; response starts with "
            f"{_response_excerpt(content)!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"{stage} must return a strict JSON object: got {type(parsed).__name__}; "
            f"response starts with {_response_excerpt(content)!r}"
        )
    return parsed, response.provider, {
        "stage": stage,
        "provider": response.provider,
        "model": response.model,
        "duration_ms": duration_ms,
        "input_messages": messages,
        "response_text": response.text,
        "parsed_json": parsed,
    }


def _json_decode_message(exc: json.JSONDecodeError) -> str:
    return exc.msg.removesuffix(" at")


def _response_excerpt(content: str, limit: int = 240) -> str:
    excerpt = " ".join(content.strip().split())
    if len(excerpt) <= limit:
        return excerpt
    return f"{excerpt[:limit]}..."
