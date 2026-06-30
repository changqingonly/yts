"""
Explicit Pro workflow fixture backend for local UI demos.

This backend is only selected with YTS_INFERENCE_BACKEND=pro-fixture. It is not a
fallback for real model failures.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .port import TextResult


class ProFixtureBackend:
    name = "pro-fixture"

    def __init__(self) -> None:
        self.payloads = deepcopy(_PAYLOADS)

    async def generate_text(self, messages, *, model=None, fallbacks=None, response_format=None) -> TextResult:
        content = messages[-1]["content"] if messages else ""
        marker = "YTS_PRO_STAGE:"
        if marker not in content:
            raise ValueError("pro-fixture requires YTS_PRO_STAGE marker")
        stage = content.split(marker, 1)[1].splitlines()[0].strip()
        payload = self.payloads.get(stage)
        if payload is None:
            raise ValueError(f"pro-fixture has no payload for stage: {stage}")
        return TextResult(
            text=json.dumps(payload, ensure_ascii=False),
            provider="pro-fixture",
            model="pro-fixture",
        )

    async def generate_image(self, prompt: str) -> bytes:
        raise NotImplementedError("pro-fixture image not supported")

    async def generate_speech(self, text: str) -> bytes:
        raise NotImplementedError("pro-fixture speech not supported")

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:
        raise NotImplementedError("pro-fixture music not supported")


def _style_candidate(identifier: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "template_id": "mandarin_pop_ballad",
        "label": "华语抒情流行",
        "suno_tags": ["Mandopop", "emotional pop"],
        "bpm_range": {"min": 80, "max": 96},
        "groove": "slow 4/4 ballad pulse",
        "vocal_profile": "intimate lead vocal",
        "instrumentation": ["piano", "warm strings"],
        "production_notes": ["keep the first verse sparse", "lift the final chorus"],
        "fit_score": 4.7,
        "fit_reason": "雨天怀旧叙事需要克制、旋律性强的流行表达。",
        "risk": "过度煽情会削弱故事质感。",
    }


_PAYLOADS: dict[str, dict[str, Any]] = {
    "parse_intent": {
        "raw_query": "下雨的午后，大雨倾盆，思念远方的故人",
        "retrieval_query": "雨天午后 思念 故人",
        "positive_terms": ["大雨", "故人", "甜蜜往事"],
        "retrieval_tokens": ["雨天", "午后", "故人"],
        "scene_cues": ["雨天午后"],
        "emotion_cues": ["思念", "怀旧"],
        "style_cues": ["华语流行"],
        "negative_terms": [],
        "negative_categories": [],
        "language": "zh",
        "genre": "Mandopop",
    },
    "build_song_brief": {
        "core_story": "雨中想起远方故人",
        "narrative_perspective": "第一人称独唱",
        "target_form": "完整情绪流行歌",
        "emotion_arc": ["潮湿午后", "甜蜜回忆", "克制告别"],
        "duet_allowed": False,
        "required_devices": [],
        "forbidden_devices": ["duet"],
    },
    "plan_music_style": {
        "style_candidates": [
            _style_candidate("mainstream_pop"),
            {
                **_style_candidate("indie_pop"),
                "label": "独立民谣流行",
                "suno_tags": ["indie folk pop", "acoustic guitar"],
                "fit_score": 4.1,
                "fit_reason": "适合雨天画面，但副歌爆发力弱于主流流行。",
                "risk": "可能让 Hook 记忆点不够强。",
            },
        ],
        "selected_style_id": "mainstream_pop",
        "selection_reason": "主流抒情流行最能承接雨天怀旧故事、慢热结构和重复 Hook。",
        "negative_tags": ["EDM drop", "duet vocal"],
    },
    "hook_lab": {
        "candidates": [
            {"hook": "雨落旧窗前", "score": 4.6, "reason": "短、可重复、有画面"},
            {"hook": "想你在远方", "score": 3.8, "reason": "直接但略普通"},
        ],
        "selected_hook": "雨落旧窗前",
        "hook_strategy": "副歌第一句出现，Final Chorus 加强重复。",
    },
    "draft_structure_blueprints": {
        "blueprints": [
            {
                "id": "slow_burn_pop",
                "mode": "ballad_slow_build",
                "sections": [
                    "Verse1",
                    "Verse2",
                    "PreChorus1",
                    "Chorus1",
                    "Bridge",
                    "Chorus2",
                    "Outro",
                ],
                "section_roles": {"Verse1": "雨中入画", "Chorus1": "Hook 释放"},
                "line_budget": {"Verse1": 4, "Verse2": 4, "Chorus1": 6},
                "energy_curve": {
                    "Verse1": 1,
                    "Verse2": 2,
                    "PreChorus1": 3,
                    "Chorus1": 4,
                    "Bridge": 3,
                    "Chorus2": 5,
                    "Outro": 1,
                },
                "hook_placement": ["Chorus1", "Chorus2"],
                "vocal_plan": {"mode": "solo", "forbidden_meta_tags": ["duet harmony"]},
                "risk": "节奏偏慢",
            },
            {
                "id": "classic_pop",
                "mode": "classic_pop_full",
                "sections": [
                    "Verse 1",
                    "Pre-Chorus",
                    "Chorus",
                    "Verse 2",
                    "Bridge",
                    "Final Chorus",
                    "Outro",
                ],
                "section_roles": {
                    "Verse 1": "开场叙事",
                    "Pre-Chorus": "情绪抬升",
                    "Chorus": "Hook 释放",
                    "Verse 2": "故事推进",
                    "Bridge": "转折",
                    "Final Chorus": "最终释放",
                    "Outro": "收束",
                },
                "line_budget": {
                    "Verse 1": 4,
                    "Pre-Chorus": 2,
                    "Chorus": 4,
                    "Verse 2": 4,
                    "Bridge": 2,
                    "Final Chorus": 4,
                    "Outro": 2,
                },
                "energy_curve": {
                    "Verse 1": 1,
                    "Pre-Chorus": 3,
                    "Chorus": 4,
                    "Verse 2": 2,
                    "Bridge": 3,
                    "Final Chorus": 5,
                    "Outro": 1,
                },
                "hook_placement": ["Chorus", "Final Chorus"],
            },
        ]
    },
    "critique_structure": {
        "selected_blueprint_id": "slow_burn_pop",
        "critic_notes": ["最贴合雨天怀旧叙事", "Hook 不应过早暴露"],
        "rejected": [{"id": "classic_pop", "reason": "较普通"}],
    },
    "plan_style_prompt": {
        "style_family": {"id": "mainstream_pop", "label": "主流流行", "template_id": "mandarin_pop_ballad"},
        "style_prompt_draft": "Mandopop, 88 BPM, intimate lead vocal, piano, warm strings",
        "style_components": ["Mandopop", "88 BPM", "intimate lead vocal", "piano", "warm strings"],
        "lyric_guidance": {
            "language": "Chinese",
            "required_sections": [
                "Verse 1",
                "Verse 2",
                "Pre-Chorus",
                "Chorus",
                "Bridge",
                "Final Chorus",
                "Outro",
            ],
            "hook_policy": "Chorus and Final Chorus repeat selected hook",
            "mood_arc": "rain memory -> warm ache -> quiet release",
        },
        "negative_terms": [],
        "source_signals": ["华语流行"],
    },
    "generate_lyrics": {
        "structure_mode": "ballad_slow_build",
        "structure": ["Verse 1", "Verse 2", "Pre-Chorus", "Chorus", "Bridge", "Final Chorus", "Outro"],
        "title": "雨中旧窗",
        "style_prompt": "Mandopop, 88 BPM, intimate lead vocal, piano, warm strings",
        "lyric_prompt": (
            "[Verse 1]\n"
            "雨落旧窗前\n"
            "午后的城慢慢暗下来\n"
            "旧照片在抽屉里微微发亮\n"
            "我把你的名字藏进雨声\n\n"
            "[Chorus]\n"
            "雨落旧窗前\n"
            "雨落旧窗前\n"
            "甜蜜往事在心上盘旋\n"
            "远方故人你是否听见\n\n"
            "[Final Chorus]\n"
            "雨落旧窗前\n"
            "雨落旧窗前\n"
            "让这场大雨替我抵达你身边"
        ),
        "hook": "雨落旧窗前",
        "clip_suggestion": {"start_section": "Chorus", "duration_seconds": 15, "reason": "副歌 Hook 清晰。"},
        "used_card_ids": [],
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
        "overall_score": 4.5,
        "scores": {
            "hook_match": 5,
            "structure_match": 5,
            "constraint_safety": 5,
            "emotion_arc": 5,
            "singability": 4,
            "suno_format": 5,
        },
        "violations": [],
        "repair_targets": [],
        "main_issues": [],
        "suggestions": [],
        "rationale": "歌词满足 Pro 蓝图和 Hook 要求。",
    },
    "refine_title": {
        "original_title": "雨中旧窗",
        "final_title": "雨中故人",
        "title_candidates": [
            {"title": "雨中故人", "kind": "hook_story", "reason": "贴合雨天与故人线索。", "selected": True}
        ],
        "selection_reason": "更准确覆盖核心故事。",
    },
}
