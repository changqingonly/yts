from __future__ import annotations

import pytest
from yts_core.orchestration.style_templates import (
    STYLE_TEMPLATES,
    match_style_templates,
)


def test_style_template_catalog_contains_31_lss_large_rules() -> None:
    assert len(STYLE_TEMPLATES) == 31
    assert {template.template_id for template in STYLE_TEMPLATES} >= {
        "short_video_folk_pop",
        "mandarin_pop_ballad",
        "cpop_rnb",
    }


def test_match_style_templates_prefers_precise_lss_scene_matches() -> None:
    matches = match_style_templates(
        user_prompt="春节民俗短视频唢呐卡点",
        intent={
            "retrieval_query": "春节 民俗 唢呐",
            "positive_terms": ["唢呐", "年节"],
            "scene_cues": ["春节"],
            "emotion_cues": [],
            "style_cues": [],
        },
        song_brief={
            "core_story": "春节团圆",
            "emotion_arc": ["热闹"],
            "target_form": "短视频 Hook 歌",
        },
    )

    assert matches[0]["template_id"] == "short_video_folk_pop"
    assert set(matches[0]["match_signals"]) >= {"唢呐", "年节", "民俗"}
    assert "Chinese festive folk pop" in matches[0]["components"]


def test_match_style_templates_keeps_mainstream_baseline_for_plain_requests() -> None:
    matches = match_style_templates(
        user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
        intent={
            "retrieval_query": "雨天午后 思念 故人",
            "positive_terms": ["大雨", "故人"],
            "scene_cues": ["雨天午后"],
            "emotion_cues": ["思念", "怀旧"],
            "style_cues": ["华语流行"],
        },
        song_brief={
            "core_story": "雨中想起远方故人",
            "emotion_arc": ["潮湿午后", "甜蜜回忆", "克制告别"],
            "target_form": "完整情绪流行歌",
        },
    )

    ids = [match["template_id"] for match in matches]
    assert "mandarin_pop_ballad" in ids


def test_match_style_templates_returns_candidate_seed_fields() -> None:
    [match, *_] = match_style_templates(
        user_prompt="想要丝滑暧昧的华语 R&B",
        intent={
            "retrieval_query": "华语 R&B 暧昧",
            "positive_terms": ["暧昧"],
            "scene_cues": [],
            "emotion_cues": ["暧昧"],
            "style_cues": ["R&B"],
        },
        song_brief={
            "core_story": "暧昧拉扯",
            "emotion_arc": ["克制", "升温"],
            "target_form": "完整情绪流行歌",
        },
    )

    assert match["template_id"] == "cpop_rnb"
    assert match["label"] == "中文 R&B"
    assert match["bpm_range"] == {"min": 82, "max": 90}
    assert match["suno_tags"][0] == "Mandarin contemporary R&B pop"
    assert match["groove"]
    assert match["vocal_profile"]
    assert match["instrumentation"]
    assert match["production_notes"]
    assert match["lyric_hint"]


def test_style_template_catalog_rejects_duplicate_template_ids(monkeypatch) -> None:
    import yts_core.orchestration.style_templates as style_templates

    duplicate = style_templates.StyleTemplate(
        template_id="mandarin_pop_ballad",
        label="Duplicate",
        keywords=("duplicate",),
        components=(
            "Mandopop",
            "96 BPM",
            "clear lead vocal",
            "piano",
            "modern polished production",
        ),
        lyric_hint="duplicate",
    )

    monkeypatch.setattr(style_templates, "STYLE_TEMPLATES", (*STYLE_TEMPLATES, duplicate))

    with pytest.raises(ValueError, match="style template ids must be unique"):
        style_templates.validate_style_template_catalog()
