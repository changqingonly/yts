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
    "plan_music_style",
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


def _style_candidate(identifier: str, bpm_range=None) -> dict:
    return {
        "id": identifier,
        "template_id": "mandarin_pop_ballad",
        "label": "华语抒情流行",
        "suno_tags": ["Mandopop", "emotional pop"],
        "bpm_range": {"min": 80, "max": 96} if bpm_range is None else bpm_range,
        "groove": "slow 4/4 ballad pulse",
        "vocal_profile": "intimate lead vocal",
        "instrumentation": ["piano", "warm strings"],
        "production_notes": ["keep the first verse sparse", "lift the final chorus"],
        "fit_score": 4.7,
        "fit_reason": "雨天怀旧叙事需要克制、旋律性强的流行表达。",
        "risk": "过度煽情会削弱故事质感。",
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
    assert result.summary.prompt_pack["pack_id"] == "pro_lyrics"
    assert result.summary.prompt_pack["version"]
    assert result.summary.prompt_pack["sha256"]
    assert set(result.model_dump()) == set(CreationResult.model_fields)
    assert backend.called_stages == [
        "parse_intent",
        "build_song_brief",
        "plan_music_style",
        "hook_lab",
        "draft_structure_blueprints",
        "critique_structure",
        "plan_style_prompt",
        "generate_lyrics",
        "review_quality",
        "refine_title",
    ]


@pytest.mark.asyncio
async def test_run_creation_passes_style_template_candidates_to_music_style_planner() -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend()

    await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    payload = backend.input_payloads["plan_music_style"]
    template_ids = [item["template_id"] for item in payload["style_template_candidates"]]
    assert "mandarin_pop_ballad" in template_ids
    assert payload["style_template_candidates"][0]["components"]


@pytest.mark.asyncio
async def test_structure_planner_receives_machine_readable_hook_placement_contract() -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend()

    await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    contract = backend.input_payloads["draft_structure_blueprints"]["structure_contract"]
    hook_contract = contract["hook_placement"]
    assert hook_contract["repeat_sections_must_be_unique"] is True
    assert hook_contract["repeat_sections_must_exclude_first_appearance"] is True
    assert hook_contract["section_references_must_exactly_match_sections"] is True
    assert hook_contract["allowed_object_keys"] == [
        "first_appearance",
        "repeat_sections",
        "strategy",
        "reason",
        "notes",
    ]
    assert hook_contract["valid_repeat_example"]["first_appearance"] == "Chorus"
    assert "Chorus" not in hook_contract["valid_repeat_example"]["repeat_sections"]


@pytest.mark.asyncio
async def test_generate_lyrics_receives_compact_context_without_duplicate_plans() -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend()

    await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    payload = backend.input_payloads["generate_lyrics"]
    assert set(payload) == {"generation_context"}

    context = payload["generation_context"]
    assert set(context) == {
        "user_prompt",
        "story",
        "style",
        "hook",
        "structure",
        "constraints",
    }
    assert "professional_plan" not in json.dumps(context, ensure_ascii=False)
    assert "structure_blueprints" not in json.dumps(context, ensure_ascii=False)
    assert "style_candidates" not in json.dumps(context, ensure_ascii=False)
    assert context["style"]["style_prompt"] == _PAYLOADS["plan_style_prompt"]["style_prompt_draft"]
    assert context["hook"]["selected_hook"] == _PAYLOADS["hook_lab"]["selected_hook"]
    assert context["structure"]["sections"] == [
        "Verse 1",
        "Verse 2",
        "Pre-Chorus",
        "Chorus",
        "Bridge",
        "Final Chorus",
        "Outro",
    ]


@pytest.mark.asyncio
async def test_review_quality_receives_compact_review_context_without_duplicate_plans() -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend()

    await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    payload = backend.input_payloads["review_quality"]
    assert set(payload) == {"review_context"}

    context = payload["review_context"]
    assert set(context) == {"user_prompt", "generation", "expected"}
    assert set(context["expected"]) == {
        "selected_hook",
        "structure",
        "constraints",
        "emotion_arc",
        "style_prompt",
    }
    serialized = json.dumps(context, ensure_ascii=False)
    assert "professional_plan" not in serialized
    assert "style_candidates" not in serialized
    assert "structure_blueprints" not in serialized
    assert "structure_critique" not in serialized
    assert context["expected"]["selected_hook"] == _PAYLOADS["hook_lab"]["selected_hook"]
    assert context["expected"]["structure"]["sections"] == [
        "Verse 1",
        "Verse 2",
        "Pre-Chorus",
        "Chorus",
        "Bridge",
        "Final Chorus",
        "Outro",
    ]


@pytest.mark.asyncio
async def test_review_quality_requires_dimension_scores_and_repair_targets() -> None:
    service._graph_cache.clear()
    review = deepcopy(_PAYLOADS["review_quality"])
    review.pop("scores")
    backend = _FakeProBackend(overrides={"review_quality": review})

    with pytest.raises(ValueError, match="quality_review.scores must be an object"):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("review_update", "message"),
    [
        ({"decision": "pass", "submit_suno": False}, "quality_review.pass must submit_suno"),
        ({"decision": "repair", "submit_suno": True}, "quality_review.repair must not submit_suno"),
        (
            {"decision": "repair", "submit_suno": False, "repair_targets": []},
            "quality_review.repair must include repair_targets",
        ),
        ({"decision": "block", "submit_suno": True}, "quality_review.block must not submit_suno"),
        (
            {"decision": "block", "submit_suno": False, "violations": []},
            "quality_review.block must include violations",
        ),
    ],
)
async def test_review_quality_rejects_inconsistent_decisions(
    review_update: dict,
    message: str,
) -> None:
    service._graph_cache.clear()
    review = deepcopy(_PAYLOADS["review_quality"])
    review.update(review_update)
    backend = _FakeProBackend(overrides={"review_quality": review})

    with pytest.raises(ValueError, match=message):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("music_style_plan", "message"),
    [
        (
            {
                "style_candidates": [_style_candidate("only")],
                "selected_style_id": "only",
                "selection_reason": "only candidate",
                "negative_tags": [],
            },
            "requires at least two style candidates",
        ),
        (
            {
                "style_candidates": [_style_candidate("mainstream_pop"), _style_candidate("indie_pop")],
                "selected_style_id": "missing",
                "selection_reason": "selected candidate must exist",
                "negative_tags": [],
            },
            "selected music style id not found",
        ),
        (
            {
                "style_candidates": [
                    _style_candidate("mainstream_pop", bpm_range={"min": 96, "max": 80}),
                    _style_candidate("indie_pop"),
                ],
                "selected_style_id": "mainstream_pop",
                "selection_reason": "invalid BPM range must fail",
                "negative_tags": [],
            },
            "bpm_range.min must be <= bpm_range.max",
        ),
        (
            {
                "style_candidates": [
                    {**_style_candidate("mainstream_pop"), "template_id": "missing_template"},
                    _style_candidate("indie_pop"),
                ],
                "selected_style_id": "mainstream_pop",
                "selection_reason": "invalid template id must fail",
                "negative_tags": [],
            },
            "music style candidate template_id not found",
        ),
    ],
)
async def test_run_creation_rejects_invalid_music_style_plan(
    music_style_plan: dict,
    message: str,
) -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend(overrides={"plan_music_style": music_style_plan})

    with pytest.raises(ValueError, match=message):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_run_creation_rejects_style_prompt_that_drifts_from_selected_music_style() -> None:
    service._graph_cache.clear()
    style_prompt = deepcopy(_PAYLOADS["plan_style_prompt"])
    style_prompt["style_family"] = {
        "id": "indie_pop",
        "label": "独立民谣流行",
        "template_id": "mandarin_pop_ballad",
    }
    backend = _FakeProBackend(overrides={"plan_style_prompt": style_prompt})

    with pytest.raises(ValueError, match="style prompt must use selected music style"):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_run_creation_rejects_style_prompt_that_drops_selected_template_id() -> None:
    service._graph_cache.clear()
    style_prompt = deepcopy(_PAYLOADS["plan_style_prompt"])
    style_prompt["style_family"].pop("template_id", None)
    backend = _FakeProBackend(overrides={"plan_style_prompt": style_prompt})

    with pytest.raises(ValueError, match="style_spec.style_family.template_id must not be empty"):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_run_creation_rejects_style_prompt_that_contains_negative_terms() -> None:
    service._graph_cache.clear()
    music_style_plan = deepcopy(_PAYLOADS["plan_music_style"])
    music_style_plan["negative_tags"] = [
        "female vocal",
        "duet harmony",
        "heavy distorted electric guitar",
    ]
    style_prompt = deepcopy(_PAYLOADS["plan_style_prompt"])
    style_prompt["style_prompt_draft"] = (
        "Mandopop, 88 BPM, warm female vocal, piano, warm strings, heavy distorted electric guitar"
    )
    style_prompt["negative_terms"] = ["female vocal", "duet harmony", "heavy distorted electric guitar"]
    backend = _FakeProBackend(
        overrides={"plan_music_style": music_style_plan, "plan_style_prompt": style_prompt}
    )

    with pytest.raises(ValueError, match="style prompt must not contain negative term"):
        await service.run_creation(
            CreationRequest(user_prompt="春山雨后，烟雾静谧，鸟鸣空响，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_style_prompt_planner_receives_negative_tags_as_forbidden_positive_terms() -> None:
    service._graph_cache.clear()
    music_style_plan = deepcopy(_PAYLOADS["plan_music_style"])
    music_style_plan["negative_tags"] = ["duet vocal", "heavy distorted electric guitar"]
    backend = _FakeProBackend(overrides={"plan_music_style": music_style_plan})

    await service.run_creation(
        CreationRequest(user_prompt="春山雨后，烟雾静谧，鸟鸣空响，思念远方的故人"),
        backend=backend,
    )

    contract = backend.input_payloads["plan_style_prompt"]["style_prompt_contract"]
    assert contract["forbidden_positive_terms"] == [
        "duet vocal",
        "heavy distorted electric guitar",
    ]
    assert contract["style_prompt_draft_must_avoid_forbidden_positive_terms"] is True
    assert contract["negative_terms_may_include_forbidden_terms"] is True


@pytest.mark.asyncio
async def test_run_creation_graph_cache_does_not_reuse_backend_instances_with_same_name() -> None:
    service._graph_cache.clear()
    first_backend = _FakeProBackend()
    second_payload = deepcopy(_PAYLOADS["review_quality"])
    second_payload.pop("submit_suno")
    second_backend = _FakeProBackend(overrides={"review_quality": second_payload})

    await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=first_backend,
    )

    with pytest.raises(ValueError, match="quality_review.submit_suno is required"):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=second_backend,
        )


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
        (
            {
                "blueprints": [
                    {
                        **_blueprint("bad"),
                        "hook_placement": {
                            "first_appearance": "Drop",
                            "repeat_sections": ["Chorus"],
                        },
                    },
                    _blueprint("good"),
                ]
            },
            "hook_placement.first_appearance must reference sections",
        ),
        (
            {
                "blueprints": [
                    {
                        **_blueprint("bad"),
                        "hook_placement": {
                            "first_appearance": "Chorus",
                            "repeat_sections": ["Chorus", "Chorus"],
                        },
                    },
                    _blueprint("good"),
                ]
            },
            "hook_placement.repeat_sections must reference unique sections",
        ),
        (
            {
                "blueprints": [
                    {
                        **_blueprint("bad"),
                        "hook_placement": {
                            "first_appearance": "Chorus",
                            "repeat_sections": ["Chorus"],
                        },
                    },
                    _blueprint("good"),
                ]
            },
            "hook_placement.repeat_sections must not include first_appearance",
        ),
        (
            {
                "blueprints": [
                    {
                        **_blueprint("bad"),
                        "hook_placement": {
                            "unexpected": "Chorus",
                        },
                    },
                    _blueprint("good"),
                ]
            },
            "hook_placement.unexpected is unsupported",
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
async def test_run_creation_accepts_structured_hook_placement_from_structure_planner() -> None:
    service._graph_cache.clear()
    blueprints = deepcopy(_PAYLOADS["draft_structure_blueprints"])
    blueprints["blueprints"][0]["hook_placement"] = {
        "first_appearance": "Chorus1",
        "repeat_sections": ["Final Chorus"],
        "strategy": "selected_hook appears as the opening chorus line and returns at the peak.",
    }
    blueprints["blueprints"][1]["hook_placement"] = {
        "first_appearance": "Chorus",
        "repeat_sections": ["Final Chorus"],
        "strategy": "selected_hook anchors the chorus and final chorus.",
    }
    backend = _FakeProBackend(overrides={"draft_structure_blueprints": blueprints})

    result = await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    assert result.title == "雨中故人"
    assert "critique_structure" in backend.called_stages


def test_structure_blueprint_duplicate_raw_chorus_keeps_first_reference() -> None:
    from yts_core.orchestration.validators.pro_lyrics import _blueprint_items

    normalized = _blueprint_items(
        {
            "blueprints": [
                {
                    "id": "repeat_raw_chorus",
                    "mode": "ballad_slow_build",
                    "sections": ["Verse 1", "Chorus", "Bridge", "Chorus", "Outro"],
                    "section_roles": {
                        "Verse 1": "叙事开场",
                        "Chorus": "首次 Hook",
                        "Bridge": "情绪转折",
                        "Chorus 2": "重复 Hook",
                        "Outro": "收束",
                    },
                    "line_budget": {
                        "Verse 1": 4,
                        "Chorus": 4,
                        "Bridge": 2,
                        "Chorus 2": 4,
                        "Outro": 2,
                    },
                    "energy_curve": {
                        "Verse 1": 1,
                        "Chorus": 4,
                        "Bridge": 3,
                        "Chorus 2": 5,
                        "Outro": 1,
                    },
                    "hook_placement": {
                        "first_appearance": "Chorus",
                        "repeat_sections": ["Chorus 2"],
                        "strategy": "Hook first lands in Chorus, then returns in Chorus 2.",
                    },
                    "bridge_function": "转折",
                    "vocal_plan": {"mode": "solo"},
                    "clip_strategy": "Chorus 2 starts the 15 second clip.",
                    "why_this_works": "慢热情绪在第二次副歌到达峰值。",
                    "risk": "需要避免副歌重复过密。",
                }
            ]
        }
    )[0]

    assert normalized["sections"] == ["Verse 1", "Chorus", "Bridge", "Chorus 2", "Outro"]
    assert normalized["hook_placement"]["first_appearance"] == "Chorus"
    assert normalized["hook_placement"]["repeat_sections"] == ["Chorus 2"]


@pytest.mark.asyncio
async def test_run_creation_requests_json_object_mode_for_pro_stage_calls() -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend()

    await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    assert backend.response_formats
    assert set(backend.response_formats) == {"json_object"}


@pytest.mark.asyncio
async def test_run_creation_reports_strict_json_parse_context() -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend(raw_overrides={"draft_structure_blueprints": "以下是结构蓝图：\n[]"})

    with pytest.raises(
        ValueError,
        match=r"draft_structure_blueprints must return a strict JSON object: .*line 1 column 1.*以下是结构蓝图",
    ):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_plan_music_style_reports_strict_json_parse_context() -> None:
    service._graph_cache.clear()
    malformed = (
        '{\n'
        '  "style_candidates": [\n'
        '    {"id": "mandolin_rain", "template_id": "mandarin_pop_ballad", '
        '"label": "雨中"钢琴"流行"}\n'
        '  ],\n'
        '  "selected_style_id": "mandolin_rain"\n'
        '}'
    )
    backend = _FakeProBackend(raw_overrides={"plan_music_style": malformed})

    with pytest.raises(
        ValueError,
        match=r"plan_music_style must return a strict JSON object: .*line 3 column .*mandolin_rain",
    ):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_refine_title_reports_strict_json_parse_context_for_control_characters() -> None:
    service._graph_cache.clear()
    malformed = (
        '{"original_title":"雨天的午后","final_title":"大雨思念",'
        '"title_candidates":[{"title":"大雨思念","kind":"hook_story",'
        '"reason":"第一行\n第二行","selected":true}],'
        '"selection_reason":"直接有力"}'
    )
    backend = _FakeProBackend(raw_overrides={"refine_title": malformed})

    with pytest.raises(
        ValueError,
        match=r"refine_title must return a strict JSON object: Invalid control character.*line 1 column",
    ) as exc_info:
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )

    assert "at at line" not in str(exc_info.value)


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
async def test_run_creation_rejects_generated_style_prompt_drift() -> None:
    service._graph_cache.clear()
    generation = deepcopy(_PAYLOADS["generate_lyrics"])
    generation["style_prompt"] = "Lo-fi hip-hop, dusty drums, whispered vocal"
    backend = _FakeProBackend(overrides={"generate_lyrics": generation})

    with pytest.raises(ValueError, match="style_spec style_prompt_draft"):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_run_creation_rejects_generated_lyrics_missing_required_sections() -> None:
    service._graph_cache.clear()
    generation = deepcopy(_PAYLOADS["generate_lyrics"])
    generation["lyric_prompt"] = (
        "[Verse 1]\n雨落旧窗前\n\n"
        "[Chorus]\n雨落旧窗前\n雨落旧窗前\n"
    )
    backend = _FakeProBackend(overrides={"generate_lyrics": generation})

    with pytest.raises(ValueError, match="lyric_prompt must include section tag"):
        await service.run_creation(
            CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
            backend=backend,
        )


@pytest.mark.asyncio
async def test_run_creation_postprocesses_chinese_suno_meta_text() -> None:
    service._graph_cache.clear()
    generation = deepcopy(_PAYLOADS["generate_lyrics"])
    generation["structure"] = ["Verse 1", "Verse 2", "Pre-Chorus", "Chorus", "Bridge", "Final Chorus", "Outro"]
    generation["lyric_prompt"] = (
        "[Verse 1]\n"
        "(极简钢琴单音，营造雨天回忆)\n"
        "雨落旧窗前\n"
        "午后的城慢慢暗下来\n\n"
        "[Verse 2]\n"
        "雨声牵着旧照片\n"
        "我把想念藏得轻一点\n\n"
        "[Pre-Chorus]\n"
        "云压低了整条长街\n"
        "心却被回忆慢慢点燃\n\n"
        "[Chorus]\n"
        "雨落旧窗前\n"
        "雨落旧窗前\n"
        "甜蜜往事在心上盘旋\n\n"
        "[Bridge]\n"
        "(人声淡出)\n"
        "若重逢只是梦的另一边\n\n"
        "[Final Chorus]\n"
        "雨落旧窗前\n"
        "雨落旧窗前\n"
        "让这场大雨替我抵达你身边\n\n"
        "[Outro]\n"
        "(单音吉他收尾)"
    )
    backend = _FakeProBackend(overrides={"generate_lyrics": generation})

    result = await service.run_creation(
        CreationRequest(user_prompt="一颗粽子两种乡愁"),
        backend=backend,
    )

    assert "(极简吉他单音" not in result.lyrics
    assert "(极简钢琴单音" not in result.lyrics
    assert "(人声淡出)" not in result.lyrics
    assert "(单音吉他收尾)" not in result.lyrics
    assert "男：" not in result.lyrics
    assert "女：" not in result.lyrics
    assert "合：" not in result.lyrics
    assert "[Instrumental Verse 1 | minimal piano motif]" in result.lyrics
    assert "[Bridge | vocal fades out]" in result.lyrics
    assert "[Instrumental Outro | solo acoustic guitar ending]" in result.lyrics
    assert "minimal piano motif" in result.style
    assert "vocal fades out" in result.style
    assert "solo acoustic guitar ending" in result.style


@pytest.mark.asyncio
async def test_run_creation_preserves_final_chorus_when_prior_sections_are_missing() -> None:
    service._graph_cache.clear()
    backend = _FakeProBackend()

    result = await service.run_creation(
        CreationRequest(user_prompt="下雨的午后，大雨倾盆，思念远方的故人"),
        backend=backend,
    )

    assert "[Final Chorus]" in result.lyrics
    assert "[Pre-Chorus]\n雨落旧窗前" not in result.lyrics


@pytest.mark.asyncio
async def test_run_creation_keeps_regular_lyrics_with_direction_words() -> None:
    service._graph_cache.clear()
    generation = deepcopy(_PAYLOADS["generate_lyrics"])
    generation["lyric_prompt"] = (
        "[Verse 1]\n"
        "雨声渐远我还站在路口\n"
        "你的背影慢慢走进灯火\n\n"
        "[Verse 2]\n"
        "旧伞靠在便利店门口\n"
        "我把沉默慢慢握成温柔\n\n"
        "[Pre-Chorus]\n"
        "云压低了整条长街\n"
        "心却被回忆慢慢点燃\n\n"
        "[Chorus]\n"
        "雨落旧窗前\n"
        "雨落旧窗前\n"
        "我把答案写在风里等候\n"
        "让明天替我拥抱自由\n\n"
        "[Bridge]\n"
        "若重逢只是梦的另一边\n"
        "我也感谢曾经并肩\n\n"
        "[Final Chorus]\n"
        "雨落旧窗前\n"
        "雨落旧窗前\n"
        "让这场大雨替我抵达你身边\n\n"
        "[Outro]\n"
        "雨声停在窗沿\n"
        "你仍在我心里面"
    )
    backend = _FakeProBackend(overrides={"generate_lyrics": generation})

    result = await service.run_creation(
        CreationRequest(user_prompt="雨后路口"),
        backend=backend,
    )

    assert "雨声渐远我还站在路口" in result.lyrics


@pytest.mark.asyncio
async def test_run_creation_repairs_when_quality_review_requests_repair() -> None:
    service._graph_cache.clear()
    review = deepcopy(_PAYLOADS["review_quality"])
    review["decision"] = "repair"
    review["bucket"] = "lyrics_low_quality_review"
    review["submit_suno"] = False
    review["main_issues"] = ["hook repetition too thin"]
    review["repair_targets"] = ["强化 Final Chorus 的 Hook 重复与情绪推进"]
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

    def __init__(
        self,
        overrides: dict[str, dict] | None = None,
        raw_overrides: dict[str, str] | None = None,
    ) -> None:
        self.payloads = deepcopy(_PAYLOADS)
        for stage, payload in (overrides or {}).items():
            self.payloads[stage] = payload
        self.raw_overrides = raw_overrides or {}
        self.called_stages: list[str] = []
        self.response_formats: list[str | None] = []
        self.input_payloads: dict[str, dict] = {}

    async def generate_text(self, messages, *, model=None, fallbacks=None, response_format=None) -> TextResult:
        content = messages[-1]["content"]
        marker = "YTS_PRO_STAGE:"
        if marker not in content:
            raise AssertionError(f"missing pro stage marker in prompt: {content[:120]}")
        stage = content.split(marker, 1)[1].splitlines()[0].strip()
        self.called_stages.append(stage)
        self.response_formats.append(response_format.get("type") if isinstance(response_format, dict) else None)
        input_marker = "Input JSON:\n"
        if input_marker in content:
            self.input_payloads[stage] = json.loads(content.split(input_marker, 1)[1])
        if stage in self.raw_overrides:
            return TextResult(text=self.raw_overrides[stage], provider="fake", model="fake")
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
    "plan_music_style": {
        "style_candidates": [
            _style_candidate("mainstream_pop"),
            {
                **_style_candidate("indie_pop"),
                "template_id": "mandarin_pop_ballad",
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
                "sections": ["Verse1", "Verse2", "PreChorus1", "Chorus1", "Bridge", "Final Chorus", "Outro"],
                "section_roles": {"Verse1": "雨中入画", "Chorus1": "Hook 释放"},
                "line_budget": {"Verse1": 4, "Verse2": 4, "Chorus1": 6},
                "energy_curve": {"Verse1": 1, "Verse2": 2, "PreChorus1": 3, "Chorus1": 4, "Bridge": 3, "Final Chorus": 5, "Outro": 1},
                "hook_placement": ["Chorus1", "Final Chorus"],
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
        "style_family": {"id": "mainstream_pop", "label": "主流流行", "template_id": "mandarin_pop_ballad"},
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
        "lyric_prompt": (
            "[Verse 1]\n"
            "雨落旧窗前\n"
            "午后的城慢慢暗下来\n"
            "旧照片在抽屉里微微发亮\n"
            "我把你的名字藏进雨声\n\n"
            "[Verse 2]\n"
            "街灯沿着水痕排成线\n"
            "那年伞下的笑还在耳边\n"
            "咖啡冷在熟悉的窗沿\n"
            "我学会把想念说得轻一点\n\n"
            "[Pre-Chorus]\n"
            "云压低了整条长街\n"
            "心却被回忆慢慢点燃\n\n"
            "[Chorus]\n"
            "雨落旧窗前\n"
            "雨落旧窗前\n"
            "甜蜜往事在心上盘旋\n"
            "远方故人你是否听见\n\n"
            "[Bridge]\n"
            "若重逢只是梦的另一边\n"
            "我也感谢曾经并肩\n\n"
            "[Final Chorus]\n"
            "雨落旧窗前\n"
            "雨落旧窗前\n"
            "让这场大雨替我抵达你身边\n"
            "把没说完的话唱到明天\n\n"
            "[Outro]\n"
            "雨声停在窗沿\n"
            "你仍在我心里面"
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
