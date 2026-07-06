from __future__ import annotations


def test_prompt_packs_exports_renderer_api() -> None:
    from yts_core.orchestration.prompt_packs import (
        render_prompt,
        resolve_prompt_pack,
        system_prompt,
    )

    assert callable(render_prompt)
    assert callable(resolve_prompt_pack)
    assert callable(system_prompt)


def test_active_pro_lyrics_pack_declares_style_template_and_json_safety_contract() -> None:
    from yts_core.orchestration.prompt_packs import resolve_prompt_pack

    pack = resolve_prompt_pack("pro_lyrics")

    assert pack.version == "2026-06-28.4"
    assert pack.contract_version == "pro_lyrics_schema_v15_compact_style_prompt_context"
    assert "不得包含未转义的控制字符" in pack.system_template
    assert "必须写成 \\n" in pack.system_template
    structure_prompt = pack.stage_templates["draft_structure_blueprints"]
    assert "请生成 2 个差异明显的歌曲结构蓝图" in structure_prompt
    assert "clip_strategy" not in structure_prompt
    assert "why_this_works" not in structure_prompt
    assert "每个文本字段不超过 24 个汉字或 12 个英文词" in structure_prompt
    assert "hook_placement 必须使用以下三种形态之一" in structure_prompt
    assert "repeat_sections 必须引用互不重复的 sections" in structure_prompt
    assert "repeat_sections 中的每一项必须与 sections 数组中的某一项完全一致" in structure_prompt
    assert "禁止使用 Chorus1、Chorus2、Verse1、PreChorus1 这类紧凑写法" in structure_prompt
    assert '不要写 ["Chorus", "Chorus"]' in structure_prompt
    assert "不要把 Chorus 和 Chorus 2 同时写进 repeat_sections" in structure_prompt
    assert "repeat_sections 禁止包含 first_appearance" in structure_prompt
    music_style_prompt = pack.stage_templates["plan_music_style"]
    assert "style_template_candidates 是质量基线库" in music_style_prompt
    assert "template_id 必须来自输入的 style_template_candidates" in music_style_prompt
    assert "suno_tags、instrumentation、production_notes 只能使用简短字符串" in music_style_prompt
    style_prompt = pack.stage_templates["plan_style_prompt"]
    assert (
        "请只基于 Input JSON 中的已选曲风、structure、hook、song_brief 与 intent 摘要"
        in style_prompt
    )
    assert "style_family 必须包含 id、label、template_id 三个字段" in style_prompt
    assert "required_sections 必须逐字复制 Input JSON.structure.sections" in style_prompt
    assert (
        "style_prompt_draft 不得包含 style_prompt_contract.forbidden_positive_terms" in style_prompt
    )
    assert "heavy distorted electric guitar" in style_prompt
    assert "clip_strategy" not in style_prompt
    refine_title_prompt = pack.stage_templates["refine_title"]
    assert "reason 和 selection_reason 必须是一行短句" in refine_title_prompt
    assert "不要在 reason 中引用带引号的原歌词" in refine_title_prompt
    generate_prompt = pack.stage_templates["generate_lyrics"]
    assert "请只基于 Input JSON.generation_context" in generate_prompt
    assert "style_prompt 必须逐字复制 generation_context.style.style_prompt" in generate_prompt
    assert "不要读取或补造未给出的上游候选方案" in generate_prompt
    review_prompt = pack.stage_templates["review_quality"]
    assert "请只基于 Input JSON.review_context" in review_prompt
    assert "scores 六个维度必须都是 0-5 数字" in review_prompt
    assert "repair 必须 submit_suno=false 且 repair_targets 非空" in review_prompt


def test_stage_user_prompts_do_not_repeat_global_json_contract() -> None:
    from yts_core.orchestration.prompt_packs import resolve_prompt_pack

    pack = resolve_prompt_pack("pro_lyrics")
    forbidden_contract_phrases = [
        "必须输出严格 JSON",
        "必须输出可被 json.loads",
        "输出必须可被 json.loads",
        "不要 Markdown",
        "不要解释",
    ]

    for stage, template in pack.stage_templates.items():
        repeated = [phrase for phrase in forbidden_contract_phrases if phrase in template]
        assert repeated == [], f"{stage} repeats global JSON contract: {repeated}"


def test_stage_system_prompt_extends_global_contract_instead_of_replacing_it() -> None:
    from yts_core.orchestration.prompt_packs import resolve_prompt_pack, system_prompt

    pack = resolve_prompt_pack("pro_lyrics")
    generate_lyrics_system = system_prompt(pack, "generate_lyrics")

    assert "歌词创作者" in generate_lyrics_system
    assert "必须输出严格 JSON" in generate_lyrics_system
    assert "不得包含未转义的控制字符" in generate_lyrics_system
    assert "必须写成 \\n" in generate_lyrics_system
    assert generate_lyrics_system.count("必须输出严格 JSON") == 1
    assert generate_lyrics_system.count("不要 Markdown") == 1


def test_structure_blueprints_render_schema_uses_structured_hook_placement() -> None:
    from yts_core.orchestration.prompts.pro_lyrics import _structure_blueprints_prompt

    prompt = _structure_blueprints_prompt(
        "draft_structure_blueprints",
        {
            "user_prompt": "一颗粽子两种乡愁",
            "intent": {},
            "song_brief": {},
            "music_style_plan": {},
            "hook_lab": {},
        },
    )

    assert '"first_appearance": "Chorus"' in prompt
    assert '"repeat_sections": ["Final Chorus"]' in prompt
    assert '"structure_contract"' in prompt
    assert '"repeat_sections_must_exclude_first_appearance": true' in prompt


def test_quality_review_render_schema_uses_pass_safe_empty_issue_arrays() -> None:
    from yts_core.orchestration.prompts.pro_lyrics import _quality_review_prompt

    prompt = _quality_review_prompt(
        "review_quality",
        {
            "review_context": {
                "user_prompt": "下雨的午后",
                "generation": {},
                "expected": {},
            }
        },
    )

    assert '"violations": []' in prompt
    assert '"repair_targets": []' in prompt
    assert '"violations": ["string"]' not in prompt
    assert '"repair_targets": ["string"]' not in prompt


def test_style_prompt_render_schema_preserves_selected_template_id() -> None:
    from yts_core.orchestration.prompts.pro_lyrics import _style_prompt_prompt

    prompt = _style_prompt_prompt(
        "plan_style_prompt",
        {
            "user_prompt": "一颗粽子两种乡愁",
            "intent": {},
            "music_style_plan": {
                "selected_style_id": "mainstream_pop",
                "selected_style": {"template_id": "mandarin_pop_ballad"},
                "negative_tags": ["heavy distorted electric guitar"],
            },
            "hook": {},
            "structure": {},
        },
    )

    assert '"template_id": "string"' in prompt
    assert '"line_length_hint": "string"' in prompt
    assert '"style_prompt_contract"' in prompt
    assert '"forbidden_positive_terms": ["heavy distorted electric guitar"]' in prompt
