from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

DECISION_PASS = "pass"
DECISION_REPAIR = "repair"
DECISION_BLOCK = "block"

_HOOK_PLACEMENT_SECTION_KEYS = {
    "first_appearance": "first_appearance",
    "first_section": "first_appearance",
    "initial_section": "first_appearance",
    "首次出现": "first_appearance",
}
_HOOK_PLACEMENT_SECTION_LIST_KEYS = {
    "repeat_sections": "repeat_sections",
    "repeated_sections": "repeat_sections",
    "repeats": "repeat_sections",
    "repeat_appearances": "repeat_sections",
    "重复位置": "repeat_sections",
}
_HOOK_PLACEMENT_TEXT_KEYS = {
    "strategy": "strategy",
    "reason": "reason",
    "notes": "notes",
    "description": "notes",
}


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
        "positive_terms": _string_list(
            _required_list(payload, "positive_terms", "intent"), "intent.positive_terms"
        ),
        "retrieval_tokens": _string_list(
            _required_list(payload, "retrieval_tokens", "intent"), "intent.retrieval_tokens"
        ),
        "scene_cues": _string_list(
            _required_list(payload, "scene_cues", "intent"), "intent.scene_cues"
        ),
        "emotion_cues": _string_list(
            _required_list(payload, "emotion_cues", "intent"), "intent.emotion_cues"
        ),
        "style_cues": _string_list(
            _required_list(payload, "style_cues", "intent"), "intent.style_cues"
        ),
        "negative_terms": _string_list(
            _required_list(payload, "negative_terms", "intent"), "intent.negative_terms"
        ),
        "negative_categories": _string_list(
            _required_list(payload, "negative_categories", "intent"), "intent.negative_categories"
        ),
    }


def _normalize_song_brief(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "core_story": _required_string(payload, "core_story", "song_brief"),
        "narrative_perspective": _required_string(payload, "narrative_perspective", "song_brief"),
        "target_form": _required_string(payload, "target_form", "song_brief"),
        "emotion_arc": _string_list(
            _required_list(payload, "emotion_arc", "song_brief"), "song_brief.emotion_arc"
        ),
        "duet_allowed": _required_bool(payload, "duet_allowed", "song_brief"),
        "required_devices": _string_list(
            _required_list(payload, "required_devices", "song_brief"), "song_brief.required_devices"
        ),
        "forbidden_devices": _string_list(
            _required_list(payload, "forbidden_devices", "song_brief"),
            "song_brief.forbidden_devices",
        ),
    }


def _normalize_music_style_plan(
    payload: dict[str, Any],
    style_template_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    template_ids = _style_template_candidate_ids(style_template_candidates or [])
    candidates = _music_style_candidates(payload.get("style_candidates"), template_ids)
    if len(candidates) < 2:
        raise ValueError("music style planner requires at least two style candidates")
    selected_style_id = _required_string(payload, "selected_style_id", "music_style_plan")
    selected_style = None
    for candidate in candidates:
        if candidate["id"] == selected_style_id:
            selected_style = candidate
            break
    if selected_style is None:
        raise ValueError(f"selected music style id not found: {selected_style_id}")
    return {
        "style_candidates": candidates,
        "selected_style_id": selected_style_id,
        "selected_style": selected_style,
        "selection_reason": _required_string(payload, "selection_reason", "music_style_plan"),
        "negative_tags": _string_list(
            _required_list(payload, "negative_tags", "music_style_plan"),
            "music_style_plan.negative_tags",
        ),
    }


def _style_template_candidate_ids(candidates: list[dict[str, Any]]) -> set[str]:
    template_ids: set[str] = set()
    for candidate in candidates:
        template_id = str(candidate.get("template_id") or "").strip()
        if not template_id:
            raise ValueError("style_template_candidate.template_id must not be empty")
        if template_id in template_ids:
            raise ValueError(f"style_template_candidate.template_id must be unique: {template_id}")
        template_ids.add(template_id)
    return template_ids


def _music_style_candidates(value: Any, template_ids: set[str]) -> list[dict[str, Any]]:
    items = _require_list(value, "music_style_plan.style_candidates")
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in items:
        candidate = _require_mapping(item, "music_style_plan.style_candidate")
        candidate_id = _required_string(candidate, "id", "music_style_candidate")
        if candidate_id in seen_ids:
            raise ValueError(f"music style candidate id must be unique: {candidate_id}")
        seen_ids.add(candidate_id)
        bpm_range = _normalize_bpm_range(
            _require_mapping(candidate.get("bpm_range"), "music_style_candidate.bpm_range")
        )
        suno_tags = _string_list(
            _required_list(candidate, "suno_tags", "music_style_candidate"),
            "music_style_candidate.suno_tags",
        )
        if not suno_tags:
            raise ValueError("music_style_candidate.suno_tags must not be empty")
        instrumentation = _string_list(
            _required_list(candidate, "instrumentation", "music_style_candidate"),
            "music_style_candidate.instrumentation",
        )
        if not instrumentation:
            raise ValueError("music_style_candidate.instrumentation must not be empty")
        production_notes = _string_list(
            _required_list(candidate, "production_notes", "music_style_candidate"),
            "music_style_candidate.production_notes",
        )
        template_id = _required_string(candidate, "template_id", "music_style_candidate")
        if template_ids and template_id not in template_ids:
            raise ValueError(f"music style candidate template_id not found: {template_id}")
        if "fit_score" not in candidate:
            raise ValueError("music_style_candidate.fit_score is required")
        fit_score = float(candidate["fit_score"])
        if fit_score < 0 or fit_score > 5:
            raise ValueError("music_style_candidate.fit_score must be from 0 to 5")
        out.append(
            {
                "id": candidate_id,
                "template_id": template_id,
                "label": _required_string(candidate, "label", "music_style_candidate"),
                "suno_tags": suno_tags,
                "bpm_range": bpm_range,
                "groove": _required_string(candidate, "groove", "music_style_candidate"),
                "vocal_profile": _required_string(
                    candidate, "vocal_profile", "music_style_candidate"
                ),
                "instrumentation": instrumentation,
                "production_notes": production_notes,
                "fit_score": fit_score,
                "fit_reason": _required_string(candidate, "fit_reason", "music_style_candidate"),
                "risk": _required_string(candidate, "risk", "music_style_candidate"),
            }
        )
    return out


def _normalize_bpm_range(value: Mapping[str, Any]) -> dict[str, int]:
    if "min" not in value:
        raise ValueError("music_style_candidate.bpm_range.min is required")
    if "max" not in value:
        raise ValueError("music_style_candidate.bpm_range.max is required")
    minimum = _bpm_value(value["min"], "music_style_candidate.bpm_range.min")
    maximum = _bpm_value(value["max"], "music_style_candidate.bpm_range.max")
    if minimum > maximum:
        raise ValueError("music_style_candidate.bpm_range.min must be <= bpm_range.max")
    return {"min": minimum, "max": maximum}


def _bpm_value(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if value < 40 or value > 220:
        raise ValueError(f"{label} must be from 40 to 220")
    return value


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
            "template_id": _required_string(style_family, "template_id", "style_spec.style_family"),
        },
        "style_prompt_draft": style_prompt,
        "style_components": _string_list(
            _required_list(payload, "style_components", "style_spec"), "style_spec.style_components"
        ),
        "lyric_guidance": _require_mapping(
            payload.get("lyric_guidance"), "style_spec.lyric_guidance"
        ),
        "negative_terms": _string_list(
            _required_list(payload, "negative_terms", "style_spec"), "style_spec.negative_terms"
        ),
        "source_signals": _string_list(
            _required_list(payload, "source_signals", "style_spec"), "style_spec.source_signals"
        ),
    }


def _validate_style_spec_matches_music_style(
    style_spec: Mapping[str, Any], music_style_plan: Mapping[str, Any]
) -> None:
    style_family = _require_mapping(style_spec.get("style_family"), "style_spec.style_family")
    selected_style_id = _required_string(music_style_plan, "selected_style_id", "music_style_plan")
    style_family_id = _required_string(style_family, "id", "style_spec.style_family")
    if style_family_id != selected_style_id:
        raise ValueError(
            "style prompt must use selected music style: "
            f"expected {selected_style_id!r}, got {style_family_id!r}"
        )
    selected_style = _require_mapping(
        music_style_plan.get("selected_style"), "music_style_plan.selected_style"
    )
    selected_template_id = _required_string(
        selected_style, "template_id", "music_style_plan.selected_style"
    )
    style_template_id = _required_string(style_family, "template_id", "style_spec.style_family")
    if style_template_id != selected_template_id:
        raise ValueError(
            "style prompt must preserve selected music style template_id: "
            f"expected {selected_template_id!r}, got {style_template_id!r}"
        )
    _validate_style_prompt_avoids_negative_terms(style_spec, music_style_plan)


def _validate_style_prompt_avoids_negative_terms(
    style_spec: Mapping[str, Any], music_style_plan: Mapping[str, Any]
) -> None:
    style_prompt = _required_string(style_spec, "style_prompt_draft", "style_spec")
    negative_terms = [
        *_string_list(
            _required_list(style_spec, "negative_terms", "style_spec"),
            "style_spec.negative_terms",
        ),
        *_string_list(
            _required_list(music_style_plan, "negative_tags", "music_style_plan"),
            "music_style_plan.negative_tags",
        ),
    ]
    for term in negative_terms:
        if _contains_style_term(style_prompt, term):
            raise ValueError(f"style prompt must not contain negative term: {term}")


def _contains_style_term(style_prompt: str, term: str) -> bool:
    normalized_prompt = re.sub(r"[^a-z0-9]+", " ", style_prompt.lower()).strip()
    normalized_term = re.sub(r"[^a-z0-9]+", " ", term.lower()).strip()
    if not normalized_term:
        return False
    return f" {normalized_term} " in f" {normalized_prompt} "


def _normalize_quality_review(payload: dict[str, Any]) -> dict[str, Any]:
    decision = _required_string(payload, "decision", "quality_review")
    if decision not in {DECISION_PASS, DECISION_REPAIR, DECISION_BLOCK}:
        raise ValueError("quality_review.decision must be one of: pass, repair, block")
    if "overall_score" not in payload:
        raise ValueError("quality_review.overall_score is required")
    if "safety" not in payload:
        raise ValueError("quality_review.safety is required")
    submit_suno = _required_bool(payload, "submit_suno", "quality_review")
    scores = _quality_review_scores(payload.get("scores"))
    violations = _string_list(
        _required_list(payload, "violations", "quality_review"), "quality_review.violations"
    )
    repair_targets = _string_list(
        _required_list(payload, "repair_targets", "quality_review"), "quality_review.repair_targets"
    )
    _validate_quality_review_decision(
        decision=decision,
        submit_suno=submit_suno,
        violations=violations,
        repair_targets=repair_targets,
    )
    return {
        "decision": decision,
        "bucket": _required_string(payload, "bucket", "quality_review"),
        "submit_suno": submit_suno,
        "safety": _quality_score(payload["safety"], "quality_review.safety"),
        "overall_score": _quality_score(payload["overall_score"], "quality_review.overall_score"),
        "scores": scores,
        "violations": violations,
        "repair_targets": repair_targets,
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


def _quality_review_scores(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("quality_review.scores must be an object")
    required = [
        "hook_match",
        "structure_match",
        "constraint_safety",
        "emotion_arc",
        "singability",
        "suno_format",
    ]
    scores: dict[str, float] = {}
    for key in required:
        if key not in value:
            raise ValueError(f"quality_review.scores.{key} is required")
        scores[key] = _quality_score(value[key], f"quality_review.scores.{key}")
    return scores


def _quality_score(value: Any, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{label} must be a number from 0 to 5")
    score = float(value)
    if score < 0 or score > 5:
        raise ValueError(f"{label} must be from 0 to 5")
    return score


def _validate_quality_review_decision(
    *,
    decision: str,
    submit_suno: bool,
    violations: list[str],
    repair_targets: list[str],
) -> None:
    if decision == DECISION_PASS:
        if not submit_suno:
            raise ValueError("quality_review.pass must submit_suno")
        if violations:
            raise ValueError("quality_review.pass must not include violations")
        if repair_targets:
            raise ValueError("quality_review.pass must not include repair_targets")
        return
    if decision == DECISION_REPAIR:
        if submit_suno:
            raise ValueError("quality_review.repair must not submit_suno")
        if not repair_targets:
            raise ValueError("quality_review.repair must include repair_targets")
        return
    if decision == DECISION_BLOCK:
        if submit_suno:
            raise ValueError("quality_review.block must not submit_suno")
        if not violations:
            raise ValueError("quality_review.block must include violations")
        if repair_targets:
            raise ValueError("quality_review.block must not include repair_targets")


def _normalize_title_refinement(
    payload: dict[str, Any], generation: Mapping[str, Any]
) -> dict[str, Any]:
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
        raise ValueError(
            "generation.title must not be empty when quality gate skips title refinement"
        )
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
    raw_labels = [
        str(section).strip()
        for section in _require_list(blueprint.get("sections"), "pro structure planner sections")
    ]
    normalized_labels = _normalize_blueprint_section_labels(raw_labels)
    label_map: dict[str, str] = {}
    for raw_label, normalized_label in zip(raw_labels, normalized_labels, strict=False):
        if raw_label and raw_label not in label_map:
            label_map[raw_label] = normalized_label
        label_map.setdefault(normalized_label, normalized_label)
    return label_map


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
            _require_mapping(
                normalized.get("section_roles"), "pro structure planner section_roles"
            ),
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
        normalized["hook_placement"] = _normalize_hook_placement(
            normalized.get("hook_placement"),
            section_label_map,
            normalized["sections"],
            "hook_placement",
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


def _normalize_hook_placement(
    value: Any,
    section_label_map: dict[str, str],
    sections: list[str],
    field_name: str,
) -> list[str] | str | dict[str, Any]:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _normalize_hook_placement_mapping(value, section_label_map, sections, field_name)
    if not isinstance(value, list):
        raise ValueError(f"pro structure planner {field_name} must be a list, string, or object")
    return _normalize_hook_section_list(value, section_label_map, sections, f"{field_name} entries")


def _normalize_hook_placement_mapping(
    value: Mapping[str, Any],
    section_label_map: dict[str, str],
    sections: list[str],
    field_name: str,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_key, raw_item in value.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError(f"pro structure planner {field_name} keys must not be empty")
        if key in _HOOK_PLACEMENT_SECTION_KEYS:
            _set_unique_mapping_value(
                normalized,
                _HOOK_PLACEMENT_SECTION_KEYS[key],
                _normalize_hook_section_reference(
                    raw_item, section_label_map, sections, f"{field_name}.{key}"
                ),
                field_name,
            )
            continue
        if key in _HOOK_PLACEMENT_SECTION_LIST_KEYS:
            _set_unique_mapping_value(
                normalized,
                _HOOK_PLACEMENT_SECTION_LIST_KEYS[key],
                _normalize_hook_section_list(
                    raw_item, section_label_map, sections, f"{field_name}.{key}"
                ),
                field_name,
            )
            continue
        if key in _HOOK_PLACEMENT_TEXT_KEYS:
            _set_unique_mapping_value(
                normalized,
                _HOOK_PLACEMENT_TEXT_KEYS[key],
                _required_text_value(raw_item, f"{field_name}.{key}"),
                field_name,
            )
            continue
        raise ValueError(f"pro structure planner {field_name}.{key} is unsupported")
    if "first_appearance" not in normalized:
        raise ValueError(f"pro structure planner {field_name}.first_appearance is required")
    if "repeat_sections" not in normalized:
        raise ValueError(f"pro structure planner {field_name}.repeat_sections is required")
    if normalized["first_appearance"] in normalized["repeat_sections"]:
        raise ValueError(
            f"pro structure planner {field_name}.repeat_sections must not include first_appearance"
        )
    return normalized


def _set_unique_mapping_value(
    mapping: dict[str, Any], key: str, value: Any, field_name: str
) -> None:
    if key in mapping:
        raise ValueError(f"pro structure planner {field_name}.{key} is duplicated")
    mapping[key] = value


def _required_text_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"pro structure planner {field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"pro structure planner {field_name} must not be empty")
    return text


def _normalize_hook_section_list(
    value: Any,
    section_label_map: dict[str, str],
    sections: list[str],
    field_name: str,
) -> list[str]:
    items = (
        [value]
        if isinstance(value, str)
        else _require_list(value, f"pro structure planner {field_name}")
    )
    normalized: list[str] = []
    for raw_section in items:
        section = _normalize_hook_section_reference(
            raw_section, section_label_map, sections, field_name
        )
        if section in normalized:
            raise ValueError(f"pro structure planner {field_name} must reference unique sections")
        normalized.append(section)
    if not normalized:
        raise ValueError(f"pro structure planner {field_name} must not be empty")
    return normalized


def _normalize_hook_section_reference(
    value: Any,
    section_label_map: dict[str, str],
    sections: list[str],
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"pro structure planner {field_name} must be a section string")
    raw_label = value.strip()
    section = section_label_map.get(raw_label, raw_label)
    if section not in set(sections):
        raise ValueError(f"pro structure planner {field_name} must reference sections")
    return section


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
        if (
            not isinstance(raw_value, int)
            or isinstance(raw_value, bool)
            or raw_value < 1
            or raw_value > 5
        ):
            raise ValueError(
                "pro structure planner energy_curve values must be integers from 1 to 5"
            )
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
    raise ValueError(
        "pro structure critique must include selected_blueprint_id or selected_blueprint"
    )


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
    clip_suggestion = _require_mapping(
        normalized.get("clip_suggestion"), "generation.clip_suggestion"
    )
    constraint_check = _require_mapping(
        normalized.get("constraint_check"), "generation.constraint_check"
    )
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
        if target_index < len(target_tags) and _same_section_family(
            current, target_tags[target_index]
        ):
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
    style_spec = _require_mapping(
        professional_plan.get("style_spec"), "professional_plan.style_spec"
    )
    expected_style_prompt = _required_string(style_spec, "style_prompt_draft", "style_spec")
    generated_style_prompt = str(generation.get("style_prompt") or "").strip()
    if generated_style_prompt != expected_style_prompt:
        raise ValueError(
            "pro generated style_prompt must equal style_spec style_prompt_draft: "
            f"expected {expected_style_prompt!r}, got {generated_style_prompt!r}"
        )
    selected_blueprint = _require_mapping(
        professional_plan.get("selected_blueprint"), "professional_plan.selected_blueprint"
    )
    expected_sections = _sections_from_blueprint(dict(selected_blueprint))
    generated_sections = _normalize_blueprint_section_labels(
        [
            str(section)
            for section in _require_list(generation.get("structure"), "generation.structure")
        ]
    )
    if generated_sections != expected_sections:
        raise ValueError(
            "pro generated structure must match selected_blueprint sections: "
            f"expected {expected_sections!r}, got {generated_sections!r}"
        )
    lyric_prompt = str(generation.get("lyric_prompt") or "")
    _validate_lyric_prompt_sections(lyric_prompt, expected_sections)
    _validate_hook_repetition(lyric_prompt, selected_hook, selected_blueprint)
    _validate_forbidden_meta_tags(lyric_prompt, selected_blueprint)


def _validate_lyric_prompt_sections(lyric_prompt: str, expected_sections: list[str]) -> None:
    present_tags = {
        _blueprint_section_label(match.group(1))
        for match in re.finditer(r"^\s*\[([^\]\n]+)\]", lyric_prompt, flags=re.MULTILINE)
    }
    for section in expected_sections:
        if section not in present_tags:
            raise ValueError(f"generation.lyric_prompt must include section tag [{section}]")


def _validate_hook_repetition(
    lyric_prompt: str, selected_hook: str, selected_blueprint: Mapping[str, Any]
) -> None:
    hook_sections = _expected_hook_sections(selected_blueprint)
    if not hook_sections:
        return
    section_blocks = _lyric_section_blocks(lyric_prompt)
    for section in hook_sections:
        block = section_blocks.get(section, "")
        if selected_hook not in block:
            raise ValueError(
                f"generation.lyric_prompt section [{section}] must repeat selected_hook"
            )


def _expected_hook_sections(selected_blueprint: Mapping[str, Any]) -> list[str]:
    sections = _sections_from_blueprint(dict(selected_blueprint))
    hook_placement = selected_blueprint.get("hook_placement")
    if isinstance(hook_placement, str):
        return [_blueprint_section_label(hook_placement)]
    if isinstance(hook_placement, list):
        return [
            _blueprint_section_label(str(section))
            for section in hook_placement
            if _blueprint_section_label(str(section)) in sections
        ]
    if isinstance(hook_placement, dict):
        out: list[str] = []
        first = str(hook_placement.get("first_appearance") or "").strip()
        if first:
            out.append(_blueprint_section_label(first))
        repeats = hook_placement.get("repeat_sections")
        if isinstance(repeats, list):
            out.extend(_blueprint_section_label(str(section)) for section in repeats)
        return [section for section in out if section in sections]
    return [section for section in sections if "Chorus" in section]


def _lyric_section_blocks(lyric_prompt: str) -> dict[str, str]:
    tag_matches = list(re.finditer(r"^\s*\[([^\]\n]+)\]", lyric_prompt, flags=re.MULTILINE))
    blocks: dict[str, str] = {}
    for index, match in enumerate(tag_matches):
        section = _blueprint_section_label(match.group(1))
        end = tag_matches[index + 1].start() if index + 1 < len(tag_matches) else len(lyric_prompt)
        blocks[section] = lyric_prompt[match.end() : end]
    return blocks


def _validate_forbidden_meta_tags(lyric_prompt: str, selected_blueprint: Mapping[str, Any]) -> None:
    vocal_plan = selected_blueprint.get("vocal_plan")
    if not isinstance(vocal_plan, Mapping):
        return
    forbidden = _string_list(
        vocal_plan.get("forbidden_meta_tags", []),
        "selected_blueprint.vocal_plan.forbidden_meta_tags",
    )
    lowered = lyric_prompt.lower()
    for tag in forbidden:
        if tag.lower() in lowered:
            raise ValueError(f"generation.lyric_prompt must not include forbidden meta tag: {tag}")


def _build_final_draft(*, title: str, style: str, lyrics: str) -> str:
    return f"Title: {title}\n\nStyle Prompt: {style}\n\nLyrics:\n{lyrics}"
