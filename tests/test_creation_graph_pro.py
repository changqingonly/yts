from __future__ import annotations

import json
from copy import deepcopy

import pytest
from yts_core.inference import TextResult
from yts_core.orchestration import service
from yts_core.schemas.creation import CreationRequest, CreationResult

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


def _blueprint(identifier: str, energy_curve=None) -> dict:
    return {
        "id": identifier,
        "mode": "ballad_slow_build",
        "sections": ["Verse 1", "Chorus"],
        "section_roles": {"Verse 1": "雨中入画", "Chorus": "Hook 释放"},
        "line_budget": {"Verse 1": 4, "Chorus": 4},
        "energy_curve": {"Verse 1": 1, "Chorus": 4} if energy_curve is None else energy_curve,
        "hook_placement": ["Chorus"],
    }


def _payload_without(stage: str, key: str) -> dict:
    payload = deepcopy(_PAYLOADS[stage])
    payload.pop(key)
    return payload


@pytest.mark.asyncio
async def test_run_creation_uses_pro_producer_flow_and_keeps_public_contract() -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend()

    result = await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    assert result.title == "雨中故人"
    assert result.lyrics.startswith("[Verse 1]\n雨落旧窗前")
    assert result.style.startswith("Mandopop, 88 BPM, intimate lead vocal")
    assert "Title: 雨中故人" in result.final_draft
    assert "Style Prompt: Mandopop, 88 BPM" in result.final_draft
    assert [stage.name for stage in result.summary.stages] == PRO_STAGE_ORDER
    assert result.summary.backend == "fake-pro"
    assert set(result.model_dump()) == set(CreationResult.model_fields)
    assert backend.called_stages == [
        "parse_intent",
        "build_song_brief",
        "hook_lab",
        "draft_structure_blueprints",
        "critique_structure",
        "plan_style_prompt",
        "generate_lyrics",
        "review_quality",
        "refine_title",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("blueprints", "message"),
    [
        (
            {"blueprints": [_blueprint("only")]},
            "requires at least two blueprints",
        ),
        (
            {
                "blueprints": [
                    {key: value for key, value in _blueprint("missing_id").items() if key != "id"},
                    _blueprint("good"),
                ]
            },
            "blueprint.id must not be empty",
        ),
        (
            {"blueprints": [_blueprint("bad", energy_curve=[0.2]), _blueprint("good")]},
            "energy_curve must be an object",
        ),
        (
            {"blueprints": [_blueprint("bad", energy_curve={"Verse 1": 1, "Chorus": 6}), _blueprint("good")]},
            "energy_curve values must be integers from 1 to 5",
        ),
        (
            {"blueprints": [_blueprint("bad", energy_curve={"Verse 1": 1, "Chorus": 4, "Drop": 5}), _blueprint("good")]},
            "energy_curve keys must come from sections",
        ),
    ],
)
async def test_run_creation_rejects_invalid_structure_blueprints(
    blueprints: dict,
    message: str,
) -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend(overrides={"draft_structure_blueprints": blueprints})

    with pytest.raises(ValueError, match=message):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_run_creation_rejects_generated_hook_drift() -> None:
    service._graph_cache.clear()
    generation = deepcopy(_PAYLOADS["generate_lyrics"])
    generation["hook"] = "想你在远方"
    backend = _FakeProBackend(overrides={"generate_lyrics": generation})

    with pytest.raises(ValueError, match="hook_lab selected_hook"):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_run_creation_repairs_when_quality_review_requests_repair() -> None:
    service._graph_cache.clear()
    review = deepcopy(_PAYLOADS["review_quality"])
    review["decision"] = "repair"
    review["bucket"] = "lyrics_low_quality_review"
    review["submit_suno"] = False
    review["main_issues"] = ["hook repetition too thin"]
    repaired = deepcopy(_PAYLOADS["generate_lyrics"])
    repaired["title"] = "雨中修复版"
    repaired["lyric_prompt"] = repaired["lyric_prompt"] + "\n我把回声唱得更清楚"
    backend = _FakeProBackend(overrides={"review_quality": review, "repair_lyrics": repaired})

    result = await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    assert "我把回声唱得更清楚" in result.lyrics
    assert "repair_lyrics" in backend.called_stages


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "key", "message"),
    [
        ("parse_intent", "positive_terms", "intent.positive_terms must be a list"),
        ("generate_lyrics", "style_prompt", "generation.style_prompt must not be empty"),
        ("review_quality", "submit_suno", "quality_review.submit_suno is required"),
    ],
)
async def test_run_creation_rejects_missing_required_pro_fields(
    stage: str,
    key: str,
    message: str,
) -> None:
    service._graph_cache.clear()
    payload = _payload_without(stage, key)
    backend = _FakeProBackend(overrides={stage: payload})

    with pytest.raises(ValueError, match=message):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


class _FakeProBackend:
    name = "fake-pro"

    def __init__(self, overrides: dict[str, dict] | None = None) -> None:
        self.payloads = deepcopy(_PAYLOADS)
        for stage, payload in (overrides or {}).items():
            self.payloads[stage] = payload
        self.called_stages: list[str] = []

    async def generate_text(self, messages, *, model=None, fallbacks=None) -> TextResult:
        content = messages[-1]["content"]
        marker = "YTS_PRO_STAGE:"
        if marker not in content:
            raise AssertionError(f"missing pro stage marker in prompt: {content[:120]}")
        stage = content.split(marker, 1)[1].splitlines()[0].strip()
        self.called_stages.append(stage)
        payload = self.payloads[stage]
        return TextResult(text=json.dumps(payload, ensure_ascii=False), provider="fake", model="fake")

    async def generate_image(self, prompt: str) -> bytes:
        raise NotImplementedError

    async def generate_speech(self, text: str) -> bytes:
        raise NotImplementedError

    async def generate_music(self, prompt: str, *, seconds: int = 8) -> bytes:
        raise NotImplementedError


_PAYLOADS = {
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
                "sections": ["Verse1", "Verse2", "PreChorus1", "Chorus1", "Bridge", "Chorus2", "Outro"],
                "section_roles": {"Verse1": "雨中入画", "Chorus1": "Hook 释放"},
                "line_budget": {"Verse1": 4, "Verse2": 4, "Chorus1": 6},
                "energy_curve": {"Verse1": 1, "Verse2": 2, "PreChorus1": 3, "Chorus1": 4, "Bridge": 3, "Chorus2": 5, "Outro": 1},
                "hook_placement": ["Chorus1", "Chorus2"],
                "vocal_plan": {"mode": "solo", "forbidden_meta_tags": ["duet harmony"]},
                "risk": "节奏偏慢",
            },
            {
                "id": "classic_pop",
                "mode": "classic_pop_full",
                "sections": ["Verse 1", "Pre-Chorus", "Chorus", "Verse 2", "Bridge", "Final Chorus", "Outro"],
                "section_roles": {
                    "Verse 1": "开场叙事",
                    "Pre-Chorus": "情绪抬升",
                    "Chorus": "Hook 释放",
                    "Verse 2": "故事推进",
                    "Bridge": "转折",
                    "Final Chorus": "最终释放",
                    "Outro": "收束",
                },
                "line_budget": {"Verse 1": 4, "Pre-Chorus": 2, "Chorus": 4, "Verse 2": 4, "Bridge": 2, "Final Chorus": 4, "Outro": 2},
                "energy_curve": {"Verse 1": 1, "Pre-Chorus": 3, "Chorus": 4, "Verse 2": 2, "Bridge": 3, "Final Chorus": 5, "Outro": 1},
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
        "style_family": {"id": "mainstream_pop", "label": "主流流行"},
        "style_prompt_draft": "Mandopop, 88 BPM, intimate lead vocal, piano, warm strings",
        "style_components": ["Mandopop", "88 BPM", "intimate lead vocal", "piano", "warm strings"],
        "lyric_guidance": {
            "language": "Chinese",
            "required_sections": ["Verse 1", "Verse 2", "Pre-Chorus", "Chorus", "Bridge", "Final Chorus", "Outro"],
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
        "lyric_prompt": "[Verse 1]\n雨落旧窗前\n午后的城慢慢暗下来\n旧照片在抽屉里微微发亮\n我把你的名字藏进雨声\n\n[Chorus]\n雨落旧窗前\n雨落旧窗前\n甜蜜往事在心上盘旋\n远方故人你是否听见\n\n[Final Chorus]\n雨落旧窗前\n雨落旧窗前\n让这场大雨替我抵达你身边",
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
