"""
Pro 制作人创作 LangGraph 图。

流程迁移自 lss pro lyrics workflow 主线:
validate_request → parse_intent → build_song_brief → hook_lab →
draft_structure_blueprints → critique_structure → plan_style_prompt →
generate_lyrics → review_quality → repair_lyrics → normalize_suno_format →
refine_title → build_response。

所有模型节点都通过注入的 InferenceBackend.generate_text 获取严格 JSON object。
JSON 非法、字段缺失或主线约束不满足时显式失败。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..schemas.common import StageTrace
from .state import CreationState

PRO_STAGE_ORDER = [
    "validate_request",
    "parse_intent",
    "build_song_brief",
    "hook_lab",
    "draft_structure_blueprints",
    "critique_structure",
    "plan_style_prompt",
    "generate_lyrics",
    "review_quality",
    "repair_lyrics",
    "normalize_suno_format",
    "refine_title",
    "build_response",
]

DECISION_PASS = "pass"
DECISION_REPAIR = "repair"
DECISION_BLOCK = "block"


def _append_stage(
    state: CreationState, name: str, provider: str, ok: bool = True
) -> list[StageTrace]:
    stages = list(state.get("stages", []))
    stages.append(StageTrace(name=name, ok=ok, note=provider))
    return stages


def build_creation_graph(*, backend, checkpointer=None):
    """构建并编译 Pro 创作图。backend 必传(实现 InferenceBackend.generate_text)。"""

    async def validate_request(state: CreationState) -> dict:
        user_prompt = str(state["user_prompt"]).strip()
        if not user_prompt:
            raise ValueError("user_prompt must not be empty")
        return {
            "user_prompt": user_prompt,
            "stages": _append_stage(state, "validate_request", "gate"),
        }

    async def parse_intent(state: CreationState) -> dict:
        payload, provider = await _generate_json_object(
            backend,
            "parse_intent",
            {
                "user_prompt": state["user_prompt"],
                "music_dimensions": state.get("music_dimensions", {}),
            },
            _parse_intent_prompt,
        )
        intent = _normalize_intent(payload)
        return {"intent": intent, "stages": _append_stage(state, "parse_intent", provider)}

    async def build_song_brief(state: CreationState) -> dict:
        payload, provider = await _generate_json_object(
            backend,
            "build_song_brief",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
            },
            _song_brief_prompt,
        )
        brief = _normalize_song_brief(payload)
        return {"song_brief": brief, "stages": _append_stage(state, "build_song_brief", provider)}

    async def hook_lab(state: CreationState) -> dict:
        payload, provider = await _generate_json_object(
            backend,
            "hook_lab",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
                "song_brief": _require_mapping(state["song_brief"], "song_brief"),
            },
            _hook_lab_prompt,
        )
        hook = _normalize_hook_lab(payload)
        return {"hook_lab": hook, "stages": _append_stage(state, "hook_lab", provider)}

    async def draft_structure_blueprints(state: CreationState) -> dict:
        payload, provider = await _generate_json_object(
            backend,
            "draft_structure_blueprints",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
                "song_brief": _require_mapping(state["song_brief"], "song_brief"),
                "hook_lab": _require_mapping(state["hook_lab"], "hook_lab"),
            },
            _structure_blueprints_prompt,
        )
        blueprint_items = _blueprint_items(payload)
        if len(blueprint_items) < 2:
            raise ValueError("pro structure planner requires at least two blueprints")
        return {
            "structure_blueprints": {"blueprints": blueprint_items},
            "stages": _append_stage(state, "draft_structure_blueprints", provider),
        }

    async def critique_structure(state: CreationState) -> dict:
        payload, provider = await _generate_json_object(
            backend,
            "critique_structure",
            {
                "user_prompt": state["user_prompt"],
                "song_brief": _require_mapping(state["song_brief"], "song_brief"),
                "hook_lab": _require_mapping(state["hook_lab"], "hook_lab"),
                "structure_blueprints": _require_mapping(
                    state["structure_blueprints"], "structure_blueprints"
                ),
            },
            _structure_critique_prompt,
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
            "stages": _append_stage(state, "critique_structure", provider),
        }

    async def plan_style_prompt(state: CreationState) -> dict:
        payload, provider = await _generate_json_object(
            backend,
            "plan_style_prompt",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
                "structure_plan": _require_mapping(state["structure_plan"], "structure_plan"),
                "professional_plan": _require_mapping(
                    state["professional_plan"], "professional_plan"
                ),
            },
            _style_prompt_prompt,
        )
        style_spec = _normalize_style_spec(payload)
        style_spec["professional_plan"] = _require_mapping(
            state["professional_plan"], "professional_plan"
        )
        return {
            "style_spec": style_spec,
            "style": style_spec["style_prompt_draft"],
            "stages": _append_stage(state, "plan_style_prompt", provider),
        }

    async def generate_lyrics(state: CreationState) -> dict:
        payload, provider = await _generate_json_object(
            backend,
            "generate_lyrics",
            {
                "user_prompt": state["user_prompt"],
                "intent": _require_mapping(state["intent"], "intent"),
                "structure_plan": _require_mapping(state["structure_plan"], "structure_plan"),
                "style_spec": _require_mapping(state["style_spec"], "style_spec"),
                "professional_plan": _require_mapping(
                    state["professional_plan"], "professional_plan"
                ),
            },
            _generate_lyrics_prompt,
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
            "stages": _append_stage(state, "generate_lyrics", provider),
        }

    async def review_quality(state: CreationState) -> dict:
        payload, provider = await _generate_json_object(
            backend,
            "review_quality",
            {
                "user_prompt": state["user_prompt"],
                "generation": _require_mapping(state["generation"], "generation"),
                "professional_plan": _require_mapping(
                    state["professional_plan"], "professional_plan"
                ),
            },
            _quality_review_prompt,
        )
        review = _normalize_quality_review(payload)
        return {"quality_review": review, "stages": _append_stage(state, "review_quality", provider)}

    async def repair_lyrics(state: CreationState) -> dict:
        review = _require_mapping(state["quality_review"], "quality_review")
        generation = _require_mapping(state["generation"], "generation")
        if review["decision"] != DECISION_REPAIR:
            return {
                "generation": generation,
                "quality_review": review,
                "stages": _append_stage(state, "repair_lyrics", "gate"),
            }

        payload, provider = await _generate_json_object(
            backend,
            "repair_lyrics",
            {
                "user_prompt": state["user_prompt"],
                "generation": generation,
                "quality_review": review,
                "structure_plan": _require_mapping(state["structure_plan"], "structure_plan"),
                "style_spec": _require_mapping(state["style_spec"], "style_spec"),
                "professional_plan": _require_mapping(
                    state["professional_plan"], "professional_plan"
                ),
            },
            _repair_lyrics_prompt,
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
            "stages": _append_stage(state, "repair_lyrics", provider),
        }

    async def normalize_suno_format(state: CreationState) -> dict:
        generation = _normalize_generation_format(
            _require_mapping(state["generation"], "generation"),
        )
        return {
            "generation": generation,
            "lyrics": generation["lyric_prompt"],
            "style": generation["style_prompt"],
            "title": generation["title"],
            "stages": _append_stage(state, "normalize_suno_format", "normalizer"),
        }

    async def refine_title(state: CreationState) -> dict:
        review = _require_mapping(state["quality_review"], "quality_review")
        generation = _require_mapping(state["generation"], "generation")
        if not review["submit_suno"]:
            title_refinement = _skip_title_refinement_for_quality_gate(generation, review)
            return {
                "title_refinement": title_refinement,
                "title": title_refinement["final_title"],
                "stages": _append_stage(state, "refine_title", "gate"),
            }

        payload, provider = await _generate_json_object(
            backend,
            "refine_title",
            {
                "user_prompt": state["user_prompt"],
                "generation": generation,
                "quality_review": review,
                "structure_plan": _require_mapping(state["structure_plan"], "structure_plan"),
            },
            _title_refinement_prompt,
        )
        title_refinement = _normalize_title_refinement(payload, generation)
        return {
            "title_refinement": title_refinement,
            "title": title_refinement["final_title"],
            "stages": _append_stage(state, "refine_title", provider),
        }

    async def build_response(state: CreationState) -> dict:
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

    graph = StateGraph(CreationState)
    graph.add_node("validate_request", validate_request)
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("build_song_brief", build_song_brief)
    graph.add_node("hook_lab", hook_lab)
    graph.add_node("draft_structure_blueprints", draft_structure_blueprints)
    graph.add_node("critique_structure", critique_structure)
    graph.add_node("plan_style_prompt", plan_style_prompt)
    graph.add_node("generate_lyrics", generate_lyrics)
    graph.add_node("review_quality", review_quality)
    graph.add_node("repair_lyrics", repair_lyrics)
    graph.add_node("normalize_suno_format", normalize_suno_format)
    graph.add_node("refine_title", refine_title)
    graph.add_node("build_response", build_response)

    graph.add_edge(START, "validate_request")
    graph.add_edge("validate_request", "parse_intent")
    graph.add_edge("parse_intent", "build_song_brief")
    graph.add_edge("build_song_brief", "hook_lab")
    graph.add_edge("hook_lab", "draft_structure_blueprints")
    graph.add_edge("draft_structure_blueprints", "critique_structure")
    graph.add_edge("critique_structure", "plan_style_prompt")
    graph.add_edge("plan_style_prompt", "generate_lyrics")
    graph.add_edge("generate_lyrics", "review_quality")
    graph.add_edge("review_quality", "repair_lyrics")
    graph.add_edge("repair_lyrics", "normalize_suno_format")
    graph.add_edge("normalize_suno_format", "refine_title")
    graph.add_edge("refine_title", "build_response")
    graph.add_edge("build_response", END)

    return graph.compile(checkpointer=checkpointer)


async def _generate_json_object(backend, stage: str, payload: dict[str, Any], prompt_builder) -> tuple[dict[str, Any], str]:
    response = await backend.generate_text(
        [
            {
                "role": "system",
                "content": (
                    "You are the YTS Pro lyrics workflow. Return one strict JSON object only. "
                    "Do not wrap it in markdown or add prose."
                ),
            },
            {"role": "user", "content": prompt_builder(stage, payload)},
        ]
    )
    content = _strip_json_fence(response.text)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{stage} must return a strict JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{stage} must return a strict JSON object")
    return parsed, response.provider


def _prompt(stage: str, task: str, payload: dict[str, Any], schema: Mapping[str, Any]) -> str:
    return (
        f"YTS_PRO_STAGE: {stage}\n"
        f"{task}\n\n"
        "Return JSON object matching this shape:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def _parse_intent_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "解析用户创作线索，提取检索语义、正向词、场景、情绪、风格与禁忌。",
        payload,
        {
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
    )


def _song_brief_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "像专业制作人一样先定核心故事、叙事视角、目标歌型、情绪弧线和禁忌项。",
        payload,
        {
            "core_story": "string",
            "narrative_perspective": "string",
            "target_form": "string",
            "emotion_arc": ["string"],
            "duet_allowed": False,
            "required_devices": ["string"],
            "forbidden_devices": ["string"],
        },
    )


def _hook_lab_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "生成并评估 Hook 候选，选择唯一记忆点。selected_hook 必须非空。",
        payload,
        {
            "candidates": [{"hook": "string", "score": 4.5, "reason": "string"}],
            "selected_hook": "string",
            "hook_strategy": "string",
        },
    )


def _structure_blueprints_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "生成至少两个差异化歌曲结构蓝图。每个蓝图必须包含 sections 和 section-keyed energy_curve。",
        payload,
        {
            "blueprints": [
                {
                    "id": "string",
                    "mode": "string",
                    "sections": ["Verse 1", "Chorus"],
                    "section_roles": {"Verse 1": "string"},
                    "line_budget": {"Verse 1": 4},
                    "energy_curve": {"Verse 1": 1, "Chorus": 4},
                    "hook_placement": ["Chorus"],
                    "vocal_plan": {"mode": "solo"},
                    "risk": "string",
                }
            ]
        },
    )


def _structure_critique_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "评审结构蓝图并选择最贴合当前创作线索的蓝图。",
        payload,
        {
            "selected_blueprint_id": "string",
            "selected_blueprint": {},
            "critic_notes": ["string"],
            "rejected": [{"id": "string", "reason": "string"}],
        },
    )


def _style_prompt_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "根据 Pro 结构蓝图、Hook 与用户风格线索生成 Suno style prompt 约束。",
        payload,
        {
            "style_family": {"id": "string", "label": "string"},
            "style_prompt_draft": "Genre, BPM, vocal profile, instruments, production",
            "style_components": ["string"],
            "lyric_guidance": {
                "language": "Chinese",
                "required_sections": ["Verse 1", "Chorus"],
                "hook_policy": "string",
                "mood_arc": "string",
            },
            "negative_terms": ["string"],
            "source_signals": ["string"],
        },
    )


def _generate_lyrics_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "根据 Pro 制作人蓝图、Hook Lab 和风格约束生成 Suno-ready 歌词包。hook 必须等于 selected_hook。",
        payload,
        {
            "structure_mode": "string",
            "structure": ["Verse 1", "Chorus"],
            "title": "string",
            "style_prompt": "string",
            "lyric_prompt": "[Verse 1]\\n...",
            "hook": "string",
            "clip_suggestion": {"start_section": "Chorus", "duration_seconds": 15, "reason": "string"},
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
    )


def _quality_review_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "评估歌词质量。decision 只能是 pass、repair 或 block；不要虚构通过。",
        payload,
        {
            "decision": "pass",
            "bucket": "pass_candidate",
            "submit_suno": True,
            "safety": 1,
            "overall_score": 4.0,
            "main_issues": ["string"],
            "suggestions": ["string"],
            "rationale": "string",
        },
    )


def _repair_lyrics_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "质量门禁要求修复。返回完整修复后的 Suno generation JSON，hook 仍必须等于 selected_hook。",
        payload,
        {
            "structure_mode": "string",
            "structure": ["Verse 1", "Chorus"],
            "title": "string",
            "style_prompt": "string",
            "lyric_prompt": "[Verse 1]\\n...",
            "hook": "string",
            "clip_suggestion": {"start_section": "Chorus", "duration_seconds": 15, "reason": "string"},
            "used_card_ids": ["string"],
            "constraint_check": {"suno_ready": True},
        },
    )


def _title_refinement_prompt(stage: str, payload: dict[str, Any]) -> str:
    return _prompt(
        stage,
        "在质量门禁通过后精修歌名，返回最终标题与候选理由。",
        payload,
        {
            "original_title": "string",
            "final_title": "string",
            "title_candidates": [
                {"title": "string", "kind": "hook_story", "reason": "string", "selected": True}
            ],
            "selection_reason": "string",
        },
    )


def _strip_json_fence(content: str) -> str:
    value = content.strip()
    if not value.startswith("```"):
        return value
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise TypeError(f"{label} must be a dict")


def _require_list(value: Any, label: str) -> list[Any]:
    if isinstance(value, list):
        return value
    raise ValueError(f"{label} must be a list")


def _string_list(value: Any, label: str) -> list[str]:
    items = _require_list(value, label)
    return [str(item).strip() for item in items if str(item).strip()]


def _required_list(mapping: Mapping[str, Any], key: str, label: str) -> list[Any]:
    if key not in mapping:
        raise ValueError(f"{label}.{key} must be a list")
    return _require_list(mapping.get(key), f"{label}.{key}")


def _required_bool(mapping: Mapping[str, Any], key: str, label: str) -> bool:
    if key not in mapping or not isinstance(mapping.get(key), bool):
        raise ValueError(f"{label}.{key} is required")
    return bool(mapping[key])


def _required_string(mapping: Mapping[str, Any], key: str, label: str) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise ValueError(f"{label}.{key} must not be empty")
    return value


def _normalize_intent(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw_query": _required_string(payload, "raw_query", "intent"),
        "retrieval_query": _required_string(payload, "retrieval_query", "intent"),
        "positive_terms": _string_list(_required_list(payload, "positive_terms", "intent"), "intent.positive_terms"),
        "retrieval_tokens": _string_list(_required_list(payload, "retrieval_tokens", "intent"), "intent.retrieval_tokens"),
        "scene_cues": _string_list(_required_list(payload, "scene_cues", "intent"), "intent.scene_cues"),
        "emotion_cues": _string_list(_required_list(payload, "emotion_cues", "intent"), "intent.emotion_cues"),
        "style_cues": _string_list(_required_list(payload, "style_cues", "intent"), "intent.style_cues"),
        "negative_terms": _string_list(_required_list(payload, "negative_terms", "intent"), "intent.negative_terms"),
        "negative_categories": _string_list(
            _required_list(payload, "negative_categories", "intent"), "intent.negative_categories"
        ),
    }


def _normalize_song_brief(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "core_story": _required_string(payload, "core_story", "song_brief"),
        "narrative_perspective": _required_string(
            payload, "narrative_perspective", "song_brief"
        ),
        "target_form": _required_string(payload, "target_form", "song_brief"),
        "emotion_arc": _string_list(_required_list(payload, "emotion_arc", "song_brief"), "song_brief.emotion_arc"),
        "duet_allowed": _required_bool(payload, "duet_allowed", "song_brief"),
        "required_devices": _string_list(
            _required_list(payload, "required_devices", "song_brief"), "song_brief.required_devices"
        ),
        "forbidden_devices": _string_list(
            _required_list(payload, "forbidden_devices", "song_brief"), "song_brief.forbidden_devices"
        ),
    }


def _normalize_hook_lab(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = _require_list(payload.get("candidates"), "hook_lab.candidates")
    for candidate in candidates:
        _require_mapping(candidate, "hook_lab.candidate")
    selected_hook = _required_string(payload, "selected_hook", "hook_lab")
    return {
        "candidates": candidates,
        "selected_hook": selected_hook,
        "hook_strategy": str(payload.get("hook_strategy") or "").strip(),
    }


def _normalize_style_spec(payload: dict[str, Any]) -> dict[str, Any]:
    style_family = _require_mapping(payload.get("style_family"), "style_spec.style_family")
    style_prompt = _required_string(payload, "style_prompt_draft", "style_spec")
    return {
        "style_family": {
            "id": _required_string(style_family, "id", "style_spec.style_family"),
            "label": _required_string(style_family, "label", "style_spec.style_family"),
        },
        "style_prompt_draft": style_prompt,
        "style_components": _string_list(
            _required_list(payload, "style_components", "style_spec"), "style_spec.style_components"
        ),
        "lyric_guidance": _require_mapping(
            payload.get("lyric_guidance"), "style_spec.lyric_guidance"
        ),
        "negative_terms": _string_list(_required_list(payload, "negative_terms", "style_spec"), "style_spec.negative_terms"),
        "source_signals": _string_list(
            _required_list(payload, "source_signals", "style_spec"), "style_spec.source_signals"
        ),
    }


def _normalize_quality_review(payload: dict[str, Any]) -> dict[str, Any]:
    decision = _required_string(payload, "decision", "quality_review")
    if decision not in {DECISION_PASS, DECISION_REPAIR, DECISION_BLOCK}:
        raise ValueError("quality_review.decision must be one of: pass, repair, block")
    if "overall_score" not in payload:
        raise ValueError("quality_review.overall_score is required")
    if "safety" not in payload:
        raise ValueError("quality_review.safety is required")
    return {
        "decision": decision,
        "bucket": _required_string(payload, "bucket", "quality_review"),
        "submit_suno": _required_bool(payload, "submit_suno", "quality_review"),
        "safety": int(payload["safety"]),
        "overall_score": float(payload["overall_score"]),
        "main_issues": _string_list(
            _required_list(payload, "main_issues", "quality_review"), "quality_review.main_issues"
        ),
        "suggestions": _string_list(
            _required_list(payload, "suggestions", "quality_review"), "quality_review.suggestions"
        ),
        "rationale": _required_string(payload, "rationale", "quality_review"),
        "repair_attempted": bool(payload.get("repair_attempted", False)),
        "repair_succeeded": bool(payload.get("repair_succeeded", False)),
    }


def _normalize_title_refinement(payload: dict[str, Any], generation: Mapping[str, Any]) -> dict[str, Any]:
    final_title = _required_string(payload, "final_title", "title_refinement")
    original_title = _required_string(payload, "original_title", "title_refinement")
    candidates = payload.get("title_candidates")
    if not isinstance(candidates, list):
        raise ValueError("title_refinement.title_candidates must be a list")
    for candidate in candidates:
        _require_mapping(candidate, "title_refinement.title_candidate")
    return {
        "original_title": original_title,
        "final_title": final_title,
        "title_candidates": candidates,
        "selection_reason": _required_string(payload, "selection_reason", "title_refinement"),
    }


def _skip_title_refinement_for_quality_gate(
    generation: Mapping[str, Any], review: Mapping[str, Any]
) -> dict[str, Any]:
    title = str(generation.get("title") or "").strip()
    if not title:
        raise ValueError("generation.title must not be empty when quality gate skips title refinement")
    issue_summary = "、".join(str(item) for item in review.get("main_issues", [])[:3])
    reason = "质量门禁未通过，跳过歌名精修并保留初版歌名。"
    if issue_summary:
        reason = f"{reason}主要问题：{issue_summary}。"
    return {
        "original_title": title,
        "final_title": title,
        "title_candidates": [
            {
                "title": title,
                "kind": "quality_gate_skipped",
                "reason": reason,
                "selected": True,
            }
        ],
        "selection_reason": reason,
    }


def _structure_plan_from_blueprint(
    blueprint: dict[str, Any], critique: Mapping[str, Any]
) -> dict[str, Any]:
    mode = _required_string(blueprint, "mode", "selected_blueprint")
    sections = _sections_from_blueprint(blueprint)
    critic_notes = critique.get("critic_notes")
    if not isinstance(critic_notes, list):
        raise ValueError("pro structure critique critic_notes must be a list")
    reason = "；".join(str(item).strip() for item in critic_notes if str(item).strip())
    if not reason:
        reason = "Pro 制作人评审选择该结构蓝图。"
    return {
        "recommended_mode": mode,
        "structure_candidates": [
            {
                "mode": mode,
                "score": 1.0,
                "reason": reason,
                "structure": sections,
            }
        ],
        "diversity_reason": "Pro 制作人链路先生成多候选蓝图，再由 critic 选择最终结构。",
    }


def _sections_from_blueprint(blueprint: dict[str, Any]) -> list[str]:
    sections = _require_list(blueprint.get("sections"), "pro structure planner sections")
    if not sections:
        raise ValueError("pro structure planner sections must not be empty")
    normalized = _normalize_blueprint_section_labels([str(section) for section in sections])
    if not any("Verse" in section for section in normalized):
        raise ValueError("selected pro blueprint must include a verse section")
    if not any("Chorus" in section for section in normalized):
        raise ValueError("selected pro blueprint must include a chorus section")
    return normalized


def _section_label_map_from_blueprint(blueprint: dict[str, Any]) -> dict[str, str]:
    raw_labels = [str(section).strip() for section in _require_list(blueprint.get("sections"), "pro structure planner sections")]
    normalized_labels = _normalize_blueprint_section_labels(raw_labels)
    return dict(zip(raw_labels, normalized_labels, strict=False))


def _normalize_blueprint_section_labels(labels: list[str]) -> list[str]:
    out: list[str] = []
    verse_count = 0
    pre_chorus_count = 0
    chorus_count = 0
    for raw in labels:
        label = _blueprint_section_label(raw)
        if label == "Verse":
            verse_count += 1
            label = f"Verse {verse_count}"
        elif label == "Pre-Chorus":
            pre_chorus_count += 1
            if pre_chorus_count >= 2:
                label = f"Pre-Chorus {pre_chorus_count}"
        elif label == "Chorus":
            chorus_count += 1
            if chorus_count == 2:
                label = "Chorus 2"
            elif chorus_count >= 3:
                label = "Final Chorus"
        if label:
            out.append(label)
    return out


def _blueprint_section_label(raw: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", raw.strip().lower())
    match = re.fullmatch(r"(prechorus|prech|pre)([1-9][0-9]*)", compact)
    if match:
        index = int(match.group(2))
        return "Pre-Chorus" if index == 1 else f"Pre-Chorus {index}"
    match = re.fullmatch(r"(chorus|hook)([1-9][0-9]*)", compact)
    if match:
        index = int(match.group(2))
        if index == 1:
            return "Chorus"
        if index == 2:
            return "Chorus 2"
        return "Final Chorus"
    match = re.fullmatch(r"(verse|v)([1-9][0-9]*)", compact)
    if match:
        return f"Verse {int(match.group(2))}"
    return _structure_label_from_token(raw)


def _structure_label_from_token(token: str) -> str:
    raw = re.sub(r"[（(][^）)]{1,12}[）)]\s*$", "", token.strip()).strip()
    lower = " ".join(raw.lower().replace("_", " ").replace("-", " ").split())
    compact = lower.replace(" ", "")
    mapping = {
        "intro": "Intro",
        "verse": "Verse",
        "verse 1": "Verse",
        "verse 2": "Verse 2",
        "pre": "Pre-Chorus",
        "pre chorus": "Pre-Chorus",
        "prechorus": "Pre-Chorus",
        "chorus": "Chorus",
        "hook": "Chorus",
        "final chorus": "Final Chorus",
        "bridge": "Bridge",
        "drop": "Drop",
        "instrumental": "Instrumental",
        "rap": "Rap",
        "outro": "Outro",
    }
    compact_mapping = {
        "verse1": "Verse",
        "verse01": "Verse",
        "v1": "Verse",
        "verse2": "Verse 2",
        "verse02": "Verse 2",
        "v2": "Verse 2",
        "prechorus1": "Pre-Chorus",
        "prech": "Pre-Chorus",
        "chorus1": "Chorus",
        "chorus2": "Chorus",
        "chorus3": "Chorus",
        "finalchorus": "Final Chorus",
    }
    chinese_mapping = {
        "前奏": "Intro",
        "主歌": "Verse",
        "主歌1": "Verse",
        "主歌一": "Verse",
        "主歌2": "Verse 2",
        "主歌二": "Verse 2",
        "预副歌": "Pre-Chorus",
        "预副": "Pre-Chorus",
        "副歌": "Chorus",
        "副歌1": "Chorus",
        "副歌一": "Chorus",
        "最终副歌": "Final Chorus",
        "最后副歌": "Final Chorus",
        "桥段": "Bridge",
        "间奏": "Instrumental",
        "说唱": "Rap",
        "尾声": "Outro",
    }
    return mapping.get(lower) or compact_mapping.get(compact) or chinese_mapping.get(compact) or raw


def _blueprint_items(value: dict[str, Any]) -> list[dict[str, Any]]:
    items = value.get("blueprints")
    if not isinstance(items, list):
        raise ValueError("pro structure planner blueprints must be a list")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("pro structure planner blueprint must be an object")
        normalized = dict(item)
        _required_string(normalized, "id", "blueprint")
        _required_string(normalized, "mode", "blueprint")
        section_label_map = _section_label_map_from_blueprint(normalized)
        normalized["sections"] = _sections_from_blueprint(normalized)
        normalized["section_roles"] = _normalize_section_keyed_mapping(
            _require_mapping(normalized.get("section_roles"), "pro structure planner section_roles"),
            section_label_map,
            normalized["sections"],
            "section_roles",
        )
        normalized["line_budget"] = _normalize_section_keyed_mapping(
            _require_mapping(normalized.get("line_budget"), "pro structure planner line_budget"),
            section_label_map,
            normalized["sections"],
            "line_budget",
        )
        normalized["energy_curve"] = _energy_curve_from_blueprint(normalized, section_label_map)
        normalized["hook_placement"] = _normalize_section_list(
            normalized.get("hook_placement"), section_label_map, normalized["sections"], "hook_placement"
        )
        out.append(normalized)
    return out


def _normalize_section_keyed_mapping(
    value: Any,
    section_label_map: dict[str, str],
    sections: list[str],
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed_sections = set(sections)
    normalized: dict[str, Any] = {}
    for raw_section, item in value.items():
        raw_label = str(raw_section).strip()
        section = section_label_map.get(raw_label, raw_label)
        if section not in allowed_sections:
            raise ValueError(f"pro structure planner {field_name} keys must come from sections")
        if section in normalized:
            raise ValueError(f"pro structure planner {field_name} keys must map to unique sections")
        normalized[section] = item
    return normalized


def _normalize_section_list(
    value: Any,
    section_label_map: dict[str, str],
    sections: list[str],
    field_name: str,
) -> list[str] | str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise ValueError(f"pro structure planner {field_name} must be a list or string")
    allowed_sections = set(sections)
    normalized: list[str] = []
    for raw_section in value:
        raw_label = str(raw_section).strip()
        section = section_label_map.get(raw_label, raw_label)
        if section not in allowed_sections:
            raise ValueError(f"pro structure planner {field_name} entries must come from sections")
        normalized.append(section)
    return normalized


def _energy_curve_from_blueprint(
    blueprint: dict[str, Any], section_label_map: dict[str, str]
) -> dict[str, int]:
    sections = _sections_from_blueprint(blueprint)
    energy_curve = blueprint.get("energy_curve")
    if not isinstance(energy_curve, dict):
        raise ValueError("pro structure planner energy_curve must be an object")
    allowed_sections = set(sections)
    normalized: dict[str, int] = {}
    for raw_section, raw_value in energy_curve.items():
        raw_label = str(raw_section).strip()
        section = section_label_map.get(raw_label, raw_label)
        if section not in allowed_sections:
            raise ValueError("pro structure planner energy_curve keys must come from sections")
        if not isinstance(raw_value, int) or isinstance(raw_value, bool) or raw_value < 1 or raw_value > 5:
            raise ValueError("pro structure planner energy_curve values must be integers from 1 to 5")
        if section in normalized:
            raise ValueError("pro structure planner energy_curve keys must map to unique sections")
        normalized[section] = raw_value
    return normalized


def _selected_blueprint(critique: dict[str, Any], blueprints: list[Any]) -> dict[str, Any]:
    selected = critique.get("selected_blueprint")
    if isinstance(selected, dict) and selected:
        return dict(selected)
    selected_id = str(critique.get("selected_blueprint_id") or "").strip()
    if selected_id:
        for blueprint in blueprints:
            item = _require_mapping(blueprint, "structure_blueprints.blueprint")
            if str(item.get("id") or "") == selected_id:
                return dict(item)
        raise ValueError(f"selected pro blueprint id not found: {selected_id}")
    raise ValueError("pro structure critique must include selected_blueprint_id or selected_blueprint")


def _normalize_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if normalized.get("lyrics_prompt") and not normalized.get("lyric_prompt"):
        normalized["lyric_prompt"] = normalized.pop("lyrics_prompt")
    normalized["structure"] = _normalize_blueprint_section_labels(
        [str(section) for section in _required_list(normalized, "structure", "generation")]
    )
    _required_string(normalized, "title", "generation")
    _required_string(normalized, "structure_mode", "generation")
    _required_string(normalized, "style_prompt", "generation")
    _required_string(normalized, "lyric_prompt", "generation")
    _required_string(normalized, "hook", "generation")
    clip_suggestion = _require_mapping(normalized.get("clip_suggestion"), "generation.clip_suggestion")
    constraint_check = _require_mapping(normalized.get("constraint_check"), "generation.constraint_check")
    used_card_ids = normalized.get("used_card_ids")
    if not isinstance(used_card_ids, list):
        raise ValueError("generation.used_card_ids must be a list")
    return {
        "structure_mode": str(normalized["structure_mode"]).strip(),
        "structure": normalized["structure"],
        "title": str(normalized["title"]).strip(),
        "style_prompt": str(normalized["style_prompt"]).strip(),
        "lyric_prompt": _normalize_lyrics_section_tags(
            str(normalized["lyric_prompt"]).strip(), normalized["structure"]
        ),
        "hook": str(normalized["hook"]).strip(),
        "clip_suggestion": clip_suggestion,
        "used_card_ids": used_card_ids,
        "constraint_check": constraint_check,
    }


def _normalize_generation_format(generation: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(generation)
    structure = normalized.get("structure")
    if not isinstance(structure, list) or not structure:
        raise ValueError("generation.structure must be a non-empty list")
    normalized["structure"] = _normalize_blueprint_section_labels([str(item) for item in structure])
    normalized["lyric_prompt"] = _normalize_lyrics_section_tags(
        _required_string(normalized, "lyric_prompt", "generation"), normalized["structure"]
    )
    return normalized


def _normalize_lyrics_section_tags(lyric_prompt: str, structure: Any) -> str:
    if not lyric_prompt or not isinstance(structure, list):
        return lyric_prompt
    tag_matches = list(re.finditer(r"^(\s*)\[([^\]\n]+)\]", lyric_prompt, flags=re.MULTILINE))
    if not tag_matches:
        return lyric_prompt
    target_tags = [str(section) for section in structure]
    target_index = 0
    replacements: list[str] = []
    for match in tag_matches:
        current = _blueprint_section_label(match.group(2))
        target = current
        if target_index < len(target_tags) and _same_section_family(current, target_tags[target_index]):
            target = target_tags[target_index]
            target_index += 1
        replacements.append(f"{match.group(1)}[{target}]")
    parts: list[str] = []
    last = 0
    for match, replacement in zip(tag_matches, replacements, strict=False):
        parts.append(lyric_prompt[last : match.start()])
        parts.append(replacement)
        last = match.end()
    parts.append(lyric_prompt[last:])
    return "".join(parts)


def _same_section_family(left: str, right: str) -> bool:
    left_family = re.sub(r"\s+[0-9]+$", "", left.replace("Final Chorus", "Chorus"))
    right_family = re.sub(r"\s+[0-9]+$", "", right.replace("Final Chorus", "Chorus"))
    return left_family == right_family


def _validate_generation_against_pro_plan(
    generation: Mapping[str, Any], professional_plan: Mapping[str, Any]
) -> None:
    hook_lab = _require_mapping(professional_plan.get("hook_lab"), "professional_plan.hook_lab")
    selected_hook = str(hook_lab.get("selected_hook") or "").strip()
    if not selected_hook:
        raise ValueError("professional_plan.hook_lab.selected_hook must not be empty")
    generated_hook = str(generation.get("hook") or "").strip()
    if generated_hook != selected_hook:
        raise ValueError(
            f"pro generated hook must match hook_lab selected_hook: expected {selected_hook!r}, got {generated_hook!r}"
        )


def _build_final_draft(*, title: str, style: str, lyrics: str) -> str:
    return f"Title: {title}\n\nStyle Prompt: {style}\n\nLyrics:\n{lyrics}"
