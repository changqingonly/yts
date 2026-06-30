from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StyleTemplate:
    template_id: str
    label: str
    keywords: tuple[str, ...]
    components: tuple[str, ...]
    lyric_hint: str


STYLE_TEMPLATES: tuple[StyleTemplate, ...] = (
    StyleTemplate("short_video_folk_pop", "魔性民俗短视频", ("唢呐", "锣鼓", "民俗", "年节", "秧歌", "广场舞", "民俗短视频", "魔性民俗"), ("Chinese festive folk pop", "118 BPM", "suona lead", "lively percussion", "fast rhythmic bounce", "chant hook", "short intro", "chorus-first structure", "bright energetic mix"), "chorus-first chant hook -> symmetric short Chinese lines -> festive repeatable outro"),
    StyleTemplate("gufeng", "国风流行", ("国风", "古风", "仙侠", "古装", "江湖", "山水", "古韵", "宿命"), ("Mandarin gufeng pop", "78 BPM", "clear emotional vocal", "guzheng and dizi motifs", "cinematic strings", "modern pop drums", "elegant verse", "expansive chorus", "warm reverb"), "poetic image verse -> clear modern emotion -> fateful chorus -> lingering bridge"),
    StyleTemplate("chinese_orchestral_ost", "华语影视感", ("影视感", "影视插曲", "ost", "电影感", "命运感", "角色歌", "预告"), ("Mandarin cinematic orchestral pop", "68 BPM", "emotional female vocal", "piano, full strings", "low taiko drums", "choir pad", "slow build", "dramatic final chorus", "wide film-score mix"), "visual verse -> destiny-scale chorus -> lower bridge -> dramatic final release"),
    StyleTemplate("mandarin_pop_ballad", "中文流行抒情", ("中文流行抒情", "抒情", "情歌", "失恋", "毕业", "温情", "释怀", "告别", "怀旧", "思念"), ("Mandarin emotional pop ballad", "72 BPM", "warm intimate vocal", "piano-led arrangement", "soft strings", "gentle drums", "sparse verse", "soaring final chorus", "modern polished mix"), "concrete memory verse -> repeatable core chorus line -> bridge turns from holding on to release"),
    StyleTemplate("cantonese_pop", "粤语流行倾向", ("粤语", "粤语歌", "港风", "港乐", "香港流行", "霓虹", "旧街"), ("Cantonese-inspired pop ballad", "76 BPM", "expressive male vocal", "piano, clean electric guitar", "warm bass", "restrained verse", "emotional chorus", "90s Hong Kong pop texture", "polished mix"), "restrained city verse -> emotional chorus release -> neon-memory bridge"),
    StyleTemplate("cpop_rnb", "中文 R&B", ("中文r&b", "华语r&b", "r&b", "rnb", "R&B", "R＆B", "暧昧", "丝滑", "转音"), ("Mandarin contemporary R&B pop", "86 BPM", "smooth male vocal", "electric piano", "soft 808", "syncopated groove", "airy backing vocals", "intimate verse", "lifted chorus", "clean modern mix"), "intimate gesture verse -> smooth pre-chorus lift -> short repeated hook -> ad-lib space"),
    StyleTemplate("neo_soul_rnb", "Neo-Soul / R&B", ("neo-soul", "neosoul", "soulful", "灵魂乐", "爵士和弦", "rhodes"), ("English neo-soul R&B", "82 BPM", "smooth soulful vocal", "Rhodes piano", "warm bass", "brushed drums", "jazzy chords", "intimate groove", "layered backing vocals", "analog warm mix"), "conversational verse -> loose rhyme groove -> soulful chorus -> ad-lib final lift"),
    StyleTemplate("mandarin_trap_rap", "中文说唱 / Trap", ("中文说唱", "说唱", "rap", "trap", "rapper", "态度", "吐槽", "怼"), ("Mandarin trap rap", "140 BPM halftime feel", "confident rap vocal", "heavy 808", "crisp hi-hats", "dark synth bass", "minimal hook", "aggressive modern mix"), "short hook -> four-line rhyme groups -> second verse escalation -> final chant"),
    StyleTemplate("english_modern_pop", "English Pop", ("english pop", "英文流行", "modern pop", "sing-along"), ("English modern pop", "104 BPM", "bright female vocal", "punchy drums", "warm synth bass", "clean guitars", "catchy pre-chorus lift", "big sing-along chorus", "polished radio mix"), "detail verse -> viewpoint chorus -> title in first or last chorus line"),
    StyleTemplate("indie_pop", "Indie Pop", ("indie pop", "独立流行", "coffee", "hallway", "parking lot", "bittersweet"), ("English indie pop", "102 BPM", "soft conversational vocal", "jangly electric guitars", "warm bass", "light live drums", "bittersweet melody", "intimate verse", "sunny chorus", "analog tape texture"), "specific everyday objects -> bittersweet chorus -> slightly imperfect human ending"),
    StyleTemplate("synth_pop_80s", "Synth Pop / 80s", ("synth pop", "80s", "八十年代", "霓虹", "复古合成器", "synthwave"), ("English 80s-inspired synth pop", "118 BPM", "bright lead vocal", "analog synth arpeggios", "gated drums", "pulsing bass", "nostalgic verse", "explosive neon chorus", "glossy retro mix"), "visual night verse -> short repeated hook -> neon chorus -> bright final chorus"),
    StyleTemplate("kpop_dance_pop", "K-Pop / Dance Pop", ("k-pop", "kpop", "韩式", "女团", "男团", "dance break", "rap break"), ("bilingual K-pop dance pop", "124 BPM", "energetic female group vocals", "tight electronic drums", "glossy synths", "rap break", "chant hook", "dynamic drops", "high-impact modern mix"), "cool verse -> lifted pre-chorus -> chant hook chorus -> rap break -> final drop"),
    StyleTemplate("jpop_anime_op", "J-Pop / Anime OP", ("j-pop", "jpop", "anime", "动漫op", "日系", "燃向op", "奔跑", "约定"), ("Japanese-inspired anime pop rock", "156 BPM", "youthful vocal", "fast live drums", "bright electric guitars", "piano accents", "urgent verse", "soaring chorus", "energetic anime opening mix"), "urgent verse -> promise pre-chorus -> soaring chorus -> final sprint"),
    StyleTemplate("pop_rock", "Pop Rock", ("pop rock", "流行摇滚", "摇滚流行", "合唱感", "anthemic"), ("English pop rock", "128 BPM", "raspy energetic vocal", "driving live drums", "crunchy electric guitars", "melodic bass", "anthemic chorus", "stadium-ready final chorus", "clean powerful mix"), "direct verse -> sing-along chorus -> breakdown bridge -> stadium final chorus"),
    StyleTemplate("indie_rock", "Indie Rock", ("indie rock", "独立摇滚", "garage", "车库摇滚", "raw male vocal"), ("English indie rock", "116 BPM", "raw male vocal", "live drums", "gritty rhythm guitars", "melodic lead guitar", "dynamic verse", "noisy chorus", "garage-leaning analog mix"), "fragmented verse -> direct chorus -> imperfect human phrasing -> noisy final lift"),
    StyleTemplate("shoegaze_dream_pop", "Shoegaze / Dream Pop", ("shoegaze", "dream pop", "盯鞋", "梦幻流行", "hazy", "迷幻墙"), ("dream pop shoegaze", "92 BPM", "ethereal female vocal", "washed-out guitars", "slow drums", "lush reverb", "hazy verse", "floating chorus", "wide atmospheric mix"), "few words -> image-first verse -> floating chorus -> spacious outro"),
    StyleTemplate("hard_rock_metal", "Metal / Hard Rock", ("metal", "金属", "hard rock", "硬摇滚", "重型", "double kick"), ("modern hard rock metal", "150 BPM", "powerful gritty vocal", "heavy distorted guitars", "double-kick drums", "dark bass", "tense verse", "explosive chorus", "aggressive polished mix"), "short strong verbs -> tense verse -> anthem chorus -> explosive final chorus"),
    StyleTemplate("boom_bap", "Boom Bap Hip-Hop", ("boom bap", "boombap", "老派说唱", "地下说唱", "爵士采样"), ("boom bap hip-hop", "92 BPM", "confident rap vocal", "dusty drum break", "vinyl crackle", "jazz piano sample feel", "warm bassline", "classic 90s underground mix"), "storytelling verse -> memorable spoken hook -> internal rhymes -> warm outro"),
    StyleTemplate("uk_drill", "Drill", ("uk drill", "drill", "冷感说唱", "滑动808"), ("UK drill", "142 BPM halftime", "cold rap vocal", "sliding 808 bass", "skittering hi-hats", "dark minor piano", "sparse atmosphere", "hard modern mix"), "high-density rhythm -> ambition theme -> avoid harmful content -> clipped final hook"),
    StyleTemplate("lofi_hiphop", "Lo-Fi Hip-Hop", ("lo-fi", "lofi", "lo-fi hip-hop", "学习", "雨夜独白", "黑胶噪声"), ("lo-fi hip-hop", "78 BPM", "mellow vocal", "dusty drums", "warm Rhodes chords", "vinyl crackle", "soft bass", "rainy-night atmosphere", "relaxed intimate mix"), "half-spoken short lines -> rainy memory hook -> relaxed repetition -> quiet fade"),
    StyleTemplate("big_room_edm", "EDM / Big Room", ("big room", "festival", "电音节", "edm", "build up", "drop"), ("big room EDM", "128 BPM", "powerful female vocal", "festival synths", "four-on-the-floor kick", "huge build-up", "explosive drop", "wide energetic mix"), "short verse -> build phrase -> slogan before drop -> repeated drop hook"),
    StyleTemplate("deep_house", "Deep House", ("deep house", "浩室", "夜店", "late-night club"), ("deep house", "122 BPM", "smooth airy vocal", "warm sub bass", "soft four-on-the-floor kick", "plucky synths", "late-night club groove", "spacious polished mix"), "minimal lyric phrase -> repeated atmospheric hook -> late-night groove -> sparse outro"),
    StyleTemplate("melodic_techno", "Techno", ("techno", "melodic techno", "极简人声", "hypnotic"), ("melodic techno", "126 BPM", "minimal hypnotic vocal phrases", "pulsing analog synths", "deep kick", "evolving arpeggios", "dark club atmosphere", "clean powerful mix"), "few spoken phrases -> hypnotic repetition -> evolving instrumental tension -> clean ending"),
    StyleTemplate("liquid_dnb", "Drum and Bass", ("drum and bass", "dnb", "liquid dnb", "高速鼓组"), ("liquid drum and bass", "174 BPM", "airy female vocal", "fast breakbeats", "warm sub bass", "lush pads", "emotional build", "rolling drop", "polished club mix"), "short verse -> piercing hook -> emotional build -> rolling final drop"),
    StyleTemplate("folk_singer_songwriter", "Folk / Singer-Songwriter", ("民谣", "folk", "singer-songwriter", "木吉他", "叙事", "口述"), ("English acoustic folk", "76 BPM", "honest intimate vocal", "fingerpicked acoustic guitar", "upright bass", "soft harmonica", "storytelling verse", "warm organic mix"), "specific people-place-time verse -> plain deep chorus -> quiet organic outro"),
    StyleTemplate("country_pop", "Country Pop", ("country", "乡村", "nashville", "公路", "porch", "old radio"), ("modern country pop", "96 BPM", "warm storytelling vocal", "acoustic guitar", "pedal steel", "steady drums", "big heartfelt chorus", "Nashville-style polished mix"), "concrete life detail verse -> heartfelt chorus judgment -> road-image bridge"),
    StyleTemplate("jazz_bossa", "Jazz Pop / Bossa", ("bossa", "bossanova", "bossa nova", "爵士流行", "慵懒", "lounge"), ("bossa nova jazz pop", "92 BPM", "smooth relaxed vocal", "nylon guitar", "brushed drums", "upright bass", "soft piano", "breezy romantic atmosphere", "warm lounge mix"), "short light verse -> breezy romantic hook -> understated bridge -> lounge outro"),
    StyleTemplate("funk_disco", "Funk / Disco", ("funk", "disco", "放克", "迪斯科", "slap bass", "call and response"), ("modern funk disco", "118 BPM", "playful vocal", "slap bass", "tight drums", "clean rhythm guitar", "brass stabs", "catchy chant chorus", "bright dancefloor mix"), "call-and-response verse -> chant chorus -> playful bridge -> bright final hook"),
    StyleTemplate("reggae_ska", "Reggae / Ska", ("reggae", "ska", "雷鬼", "斯卡", "offbeat", "阳光疗愈"), ("roots reggae pop", "82 BPM", "relaxed soulful vocal", "offbeat guitar skank", "warm bass", "light organ", "laid-back groove", "sunny positive chorus", "analog mix"), "warm sparse verse -> positive repeated chorus -> laid-back final refrain"),
    StyleTemplate("ambient_meditation", "Ambient / Meditation", ("ambient", "冥想", "meditation", "无词", "疗愈白噪", "放松"), ("ambient vocal piece", "60 BPM", "soft wordless female vocal pads", "slow piano", "evolving synth textures", "no drums", "spacious reverb", "calming meditative mix"), "minimal words or wordless vowels -> slow breath phrases -> calming fade"),
    StyleTemplate("cinematic_trailer_epic", "Cinematic Trailer / Epic", ("epic", "史诗", "预告片", "trailer", "战斗", "英雄", "巨幕"), ("epic cinematic trailer song", "70 BPM rising to 140 BPM", "powerful choir", "massive strings", "taiko percussion", "dramatic female lead vocal", "heroic build", "huge final climax", "widescreen mix"), "short heroic lines -> rising tension -> massive final climax -> decisive outro"),
)

_BASELINE_TEMPLATE_IDS = ("mandarin_pop_ballad",)


def validate_style_template_catalog() -> None:
    seen_ids: set[str] = set()
    for template in STYLE_TEMPLATES:
        if template.template_id in seen_ids:
            raise ValueError(f"style template ids must be unique: {template.template_id}")
        seen_ids.add(template.template_id)
        if not template.label.strip():
            raise ValueError(f"style template label must not be empty: {template.template_id}")
        if len(template.components) < 5:
            raise ValueError(f"style template components must include core Suno dimensions: {template.template_id}")
        if not template.keywords:
            raise ValueError(f"style template keywords must not be empty: {template.template_id}")
        if not template.lyric_hint.strip():
            raise ValueError(f"style template lyric_hint must not be empty: {template.template_id}")


def match_style_templates(
    *,
    user_prompt: str,
    intent: dict[str, Any],
    song_brief: dict[str, Any],
    limit: int = 6,
) -> list[dict[str, Any]]:
    validate_style_template_catalog()
    text = _source_text(user_prompt, intent, song_brief)
    scored: list[tuple[int, int, StyleTemplate, list[str]]] = []
    for index, template in enumerate(STYLE_TEMPLATES):
        signals = [keyword for keyword in template.keywords if _contains(text, keyword)]
        if signals:
            scored.append((len(signals), -index, template, signals))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = [_template_seed(template, signals) for _, _, template, signals in scored[:limit]]
    selected_ids = {item["template_id"] for item in selected}
    for template_id in _BASELINE_TEMPLATE_IDS:
        if len(selected) >= limit:
            break
        if template_id in selected_ids:
            continue
        template = _template_by_id(template_id)
        selected.append(_template_seed(template, ["baseline"]))
        selected_ids.add(template_id)
    if not selected:
        raise ValueError("style template matcher produced no candidates")
    return selected


def _template_seed(template: StyleTemplate, signals: list[str]) -> dict[str, Any]:
    components = list(template.components)
    return {
        "template_id": template.template_id,
        "label": template.label,
        "match_signals": signals,
        "components": components,
        "suno_tags": [components[0]],
        "bpm_range": _bpm_range_from_components(components),
        "groove": _groove_from_components(components),
        "vocal_profile": _first_component_matching(components, ("vocal", "voice", "choir", "chant", "rap cadence")),
        "instrumentation": _instrumentation_from_components(components),
        "production_notes": _production_notes_from_components(components),
        "lyric_hint": template.lyric_hint,
    }


def _source_text(user_prompt: str, intent: dict[str, Any], song_brief: dict[str, Any]) -> str:
    parts: list[str] = [user_prompt]
    for key in ("retrieval_query", "raw_query"):
        parts.append(str(intent.get(key) or ""))
    for key in ("positive_terms", "retrieval_tokens", "scene_cues", "emotion_cues", "style_cues"):
        value = intent.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    for key in ("core_story", "narrative_perspective", "target_form"):
        parts.append(str(song_brief.get(key) or ""))
    emotion_arc = song_brief.get("emotion_arc")
    if isinstance(emotion_arc, list):
        parts.extend(str(item) for item in emotion_arc)
    return " ".join(parts)


def _template_by_id(template_id: str) -> StyleTemplate:
    for template in STYLE_TEMPLATES:
        if template.template_id == template_id:
            return template
    raise ValueError(f"unknown style template id: {template_id}")


def _bpm_range_from_components(components: list[str]) -> dict[str, int]:
    bpm_values: list[int] = []
    for component in components:
        bpm_values.extend(int(value) for value in re.findall(r"\b([0-9]{2,3})\s*BPM\b", component, flags=re.IGNORECASE))
    if not bpm_values:
        raise ValueError("style template components must include BPM")
    center = bpm_values[0]
    return {"min": max(40, center - 4), "max": min(220, center + 4)}


def _first_component_matching(components: list[str], needles: tuple[str, ...]) -> str:
    for component in components:
        normalized = component.lower()
        if any(needle in normalized for needle in needles):
            return component
    raise ValueError(f"style template components missing expected dimension: {needles[0]}")


def _groove_from_components(components: list[str]) -> str:
    for component in components:
        normalized = component.lower()
        if any(
            marker in normalized
            for marker in ("groove", "feel", "beat", "rhythmic", "bounce", "tempo", "bpm")
        ):
            return component
    raise ValueError("style template components must include BPM or groove")


def _instrumentation_from_components(components: list[str]) -> list[str]:
    instruments: list[str] = []
    markers = (
        "piano",
        "guitar",
        "synth",
        "bass",
        "drum",
        "strings",
        "guzheng",
        "dizi",
        "pipa",
        "808",
        "percussion",
        "organ",
        "rhodes",
        "brass",
        "choir",
        "suona",
    )
    for component in components:
        if any(marker in component.lower() for marker in markers):
            instruments.append(component)
    if not instruments:
        raise ValueError("style template components must include instrumentation")
    return instruments


def _production_notes_from_components(components: list[str]) -> list[str]:
    notes = [
        component
        for component in components[1:]
        if any(
            marker in component.lower()
            for marker in (
                "mix",
                "production",
                "arrangement",
                "structure",
                "verse",
                "chorus",
                "drop",
                "build",
                "intro",
                "atmosphere",
                "groove",
                "texture",
            )
        )
    ]
    if not notes:
        raise ValueError("style template components must include production notes")
    return notes


def _contains(text: str, keyword: str) -> bool:
    return _normalize(keyword) in _normalize(text)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold().replace("＆", "&"))
