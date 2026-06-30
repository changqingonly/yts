from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SunoPostprocessResult:
    generation: dict[str, Any]
    removed_non_lyric_lines: list[str] = field(default_factory=list)
    inserted_tags: list[str] = field(default_factory=list)
    style_cues: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.removed_non_lyric_lines or self.inserted_tags or self.style_cues)


def postprocess_suno_generation(generation: Mapping[str, Any]) -> SunoPostprocessResult:
    normalized = dict(generation)
    structure = _string_list(normalized.get("structure"), "generation.structure")
    style_prompt = _required_string(normalized.get("style_prompt"), "generation.style_prompt")
    lyric_prompt = _required_string(normalized.get("lyric_prompt"), "generation.lyric_prompt")

    lyric_result = _postprocess_lyrics(lyric_prompt, structure)
    style_prompt = _augment_style_prompt(style_prompt, lyric_result.style_cues)
    normalized["lyric_prompt"] = lyric_result.lyric_prompt
    normalized["style_prompt"] = style_prompt
    _validate_no_unsafe_suno_text(normalized["lyric_prompt"])
    return SunoPostprocessResult(
        generation=normalized,
        removed_non_lyric_lines=lyric_result.removed_non_lyric_lines,
        inserted_tags=lyric_result.inserted_tags,
        style_cues=lyric_result.style_cues,
    )


@dataclass(frozen=True)
class _LyricsPostprocessResult:
    lyric_prompt: str
    removed_non_lyric_lines: list[str]
    inserted_tags: list[str]
    style_cues: list[str]


def _postprocess_lyrics(lyric_prompt: str, structure: list[str]) -> _LyricsPostprocessResult:
    rendered = _render_section_and_vocal_tags(lyric_prompt, structure)
    lines: list[str] = []
    removed: list[str] = []
    inserted: list[str] = []
    style_cues: list[str] = []
    current_section = ""

    for line in rendered.splitlines():
        stripped = line.strip()
        section = _section_from_tag(stripped)
        if section:
            current_section = section
            lines.append(line)
            continue
        if _is_markdown_separator(stripped):
            removed.append(stripped)
            continue
        direction = _direction_text(stripped, current_section)
        if direction:
            removed.append(direction)
            cue = _direction_cue(direction, current_section)
            if cue.lyric_tag and cue.lyric_tag not in inserted:
                inserted.append(cue.lyric_tag)
                lines.append(cue.lyric_tag)
            if cue.style_cue and cue.style_cue not in style_cues:
                style_cues.append(cue.style_cue)
            continue
        lines.append(line)

    return _LyricsPostprocessResult(
        lyric_prompt="\n".join(lines).strip(),
        removed_non_lyric_lines=removed,
        inserted_tags=inserted,
        style_cues=style_cues,
    )


def _render_section_and_vocal_tags(lyric_prompt: str, structure: list[str]) -> str:
    lines = lyric_prompt.splitlines()
    out: list[str] = []
    current_section = ""
    current_vocal = ""
    target_index = 0

    for line in lines:
        tag_match = re.match(r"^(\s*)\[([^\]\n]+)\]\s*$", line)
        if tag_match:
            indent, raw_tag = tag_match.groups()
            raw_section, vocal = _section_and_vocal_from_text(raw_tag)
            section = _target_section(raw_section, structure, target_index)
            if _same_section_family(raw_section, section):
                target_index = min(target_index + 1, len(structure))
            if not vocal:
                vocal = _vocal_meta_from_text(raw_tag)
            current_section = section
            current_vocal = vocal
            out.append(_format_section_tag(section, vocal, indent))
            continue

        title_match = re.match(r"^(\s*)[（(]([^）)\n]{1,40})[）)]\s*$", line)
        if title_match:
            indent, title = title_match.groups()
            raw_section, vocal = _section_and_vocal_from_text(title)
            section_is_known = raw_section != title.strip()
            if section_is_known:
                section = _target_section(raw_section, structure, target_index)
                target_index = min(target_index + 1, len(structure))
                current_section = section
                current_vocal = vocal
                out.append(_format_section_tag(section, vocal, indent))
                continue

        prefix_match = re.match(r"^(\s*)(男|男声|女|女声|合|合唱|男女|男女合唱|男女交替)[：:]\s*(.*)$", line)
        if prefix_match and current_section:
            indent, speaker, body = prefix_match.groups()
            vocal = _vocal_meta_from_text(speaker)
            if vocal and vocal != current_vocal:
                out.append(_format_section_tag(current_section, vocal, indent))
                current_vocal = vocal
            if body:
                out.append(f"{indent}{body}")
            continue

        paren_prefix = re.match(r"^(\s*)[（(](男|男声|女|女声|合|合唱|男女|男女合唱|男女交替)[）)]\s*(.*)$", line)
        if paren_prefix and current_section:
            indent, speaker, body = paren_prefix.groups()
            vocal = _vocal_meta_from_text(speaker)
            if vocal and vocal != current_vocal:
                out.append(_format_section_tag(current_section, vocal, indent))
                current_vocal = vocal
            if body:
                out.append(f"{indent}{body}")
            continue

        out.append(line)

    return "\n".join(out)


def _section_and_vocal_from_text(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in re.split(r"\s*[|]\s*", value, maxsplit=1)]
    left = parts[0]
    vocal_text = parts[1] if len(parts) > 1 else ""
    dash_parts = re.split(r"\s*[-—–_]\s*", left, maxsplit=1)
    section_text = dash_parts[0].strip()
    if not vocal_text and len(dash_parts) > 1:
        vocal_text = dash_parts[1]
    return _section_label(section_text), _vocal_meta_from_text(vocal_text)


def _target_section(raw_section: str, structure: list[str], target_index: int) -> str:
    if target_index < len(structure) and _same_section_family(raw_section, structure[target_index]):
        return structure[target_index]
    return raw_section


def _section_label(value: str) -> str:
    raw = value.strip()
    compact = re.sub(r"[\s_\-—–]+", "", raw.lower())
    match = re.fullmatch(r"(verse|v|主歌)([1-9][0-9]*|一|二|三)?", compact)
    if match:
        index = _section_index(match.group(2))
        return f"Verse {index}" if index > 1 else "Verse 1"
    match = re.fullmatch(r"(prechorus|prech|pre|预副歌|预副)([1-9][0-9]*|一|二|三)?", compact)
    if match:
        index = _section_index(match.group(2))
        return f"Pre-Chorus {index}" if index > 1 else "Pre-Chorus"
    match = re.fullmatch(r"(chorus|hook|副歌)([1-9][0-9]*|一|二|三)?", compact)
    if match:
        index = _section_index(match.group(2))
        if index <= 1:
            return "Chorus"
        if index == 2:
            return "Chorus 2"
        return "Final Chorus"
    mapping = {
        "intro": "Intro",
        "前奏": "Intro",
        "bridge": "Bridge",
        "桥段": "Bridge",
        "桥": "Bridge",
        "outro": "Outro",
        "尾声": "Outro",
        "尾奏": "Outro",
        "finalchorus": "Final Chorus",
        "最终副歌": "Final Chorus",
        "最后副歌": "Final Chorus",
        "instrumental": "Instrumental",
        "间奏": "Instrumental",
    }
    return mapping.get(compact, raw)


def _section_index(value: str | None) -> int:
    if not value:
        return 1
    chinese = {"一": 1, "二": 2, "三": 3}
    if value in chinese:
        return chinese[value]
    return int(value)


def _same_section_family(left: str, right: str) -> bool:
    return _section_family(left) == _section_family(right)


def _section_family(value: str) -> str:
    label = _section_label(value)
    if label.startswith("Pre-Chorus"):
        return "Pre-Chorus"
    if "Verse" in label:
        return "Verse"
    if "Chorus" in label:
        return "Chorus"
    return re.sub(r"\s+[0-9]+$", "", label)


def _vocal_meta_from_text(value: str) -> str:
    compact = re.sub(r"\s+", "", value.strip().lower())
    if not compact:
        return ""
    if compact in {"男", "男声", "male", "malevocal", "man"}:
        return "male vocal"
    if compact in {"女", "女声", "female", "femalevocal", "woman"}:
        return "female vocal"
    if compact in {"合", "合唱", "男女", "男女合唱", "duet", "duetharmony", "harmony"}:
        return "duet harmony"
    if "对话式对仗" in compact or "男女交替" in compact or "男女对白" in compact or "交替" in compact or "对唱" in compact:
        return "male and female alternating vocals"
    if "合唱" in compact or compact.startswith("合"):
        return "duet harmony"
    if "男" in compact and "女" in compact:
        return "male and female alternating vocals"
    if "男" in compact:
        return "male vocal"
    if "女" in compact:
        return "female vocal"
    return ""


def _format_section_tag(section: str, vocal: str = "", indent: str = "") -> str:
    suffix = f" | {vocal}" if vocal else ""
    return f"{indent}[{section}{suffix}]"


def _section_from_tag(value: str) -> str:
    match = re.match(r"^\[([^\]\n]+)\]$", value)
    if not match:
        return ""
    section, _ = _section_and_vocal_from_text(match.group(1))
    return section


def _direction_text(value: str, section: str) -> str:
    parenthetical = _parenthetical_text(value)
    if parenthetical and _looks_like_direction(parenthetical, section):
        return parenthetical
    if _looks_like_direction(value, section):
        return value
    return ""


def _parenthetical_text(value: str) -> str:
    match = re.match(r"^[（(]([^）)\n]{2,80})[）)]$", value)
    return match.group(1).strip() if match else ""


def _looks_like_direction(value: str, section: str = "") -> bool:
    if not value or len(value) > 32:
        return False
    if _looks_like_lyric_sentence(value):
        return False
    if _has_any(value, ["吉他", "钢琴", "弦乐", "鼓点", "贝斯", "编曲", "单音"]):
        return True
    if _has_any(value, ["雨声", "风声", "雷声", "海浪", "掌声", "环境音", "音效"]):
        return True
    if _has_any(value, ["哼唱", "和声", "人声", "低吟", "吟唱"]):
        return True
    if _has_any(value, ["画面", "镜头", "灯光", "舞台"]):
        return True
    if _has_any(value, ["渐远", "淡出", "渐弱", "收尾", "营造", "重复副歌", "进入桥段"]):
        return True
    return section in {"Intro", "Outro", "Instrumental"} and _has_cjk(value)


@dataclass(frozen=True)
class _Cue:
    lyric_tag: str
    style_cue: str


def _direction_cue(value: str, section: str) -> _Cue:
    if "钢琴" in value and "单音" in value:
        return _Cue(f"[Instrumental {section or 'Outro'} | minimal piano motif]", "minimal piano motif")
    if "吉他" in value or "单音" in value:
        if section == "Intro":
            return _Cue("[Intro | solo acoustic guitar]", "solo acoustic guitar intro")
        if section == "Outro":
            return _Cue("[Instrumental Outro | solo acoustic guitar ending]", "solo acoustic guitar ending")
        return _Cue(f"[Instrumental {section or 'Outro'} | solo acoustic guitar]", "solo acoustic guitar")
    if "钢琴" in value:
        return _Cue(f"[Instrumental {section or 'Outro'} | piano fades out]", "piano fades out")
    if "弦乐" in value:
        return _Cue(f"[Instrumental {section or 'Outro'} | warm strings bed]", "warm strings bed")
    if "雨声" in value or "雷声" in value:
        cue = "rain ambience and distant thunder" if "雷声" in value else "rain ambience fades out"
        return _Cue(f"[Instrumental {section or 'Outro'} | {cue}]", cue)
    if "风声" in value:
        return _Cue(f"[Instrumental {section or 'Outro'} | wind ambience]", "wind ambience")
    if "哼唱" in value or "吟唱" in value:
        return _Cue(f"[{section or 'Outro'} | soft humming fades out]", "soft humming fades out")
    if "人声" in value and ("淡出" in value or "渐远" in value or "渐弱" in value):
        return _Cue(f"[{section or 'Outro'} | vocal fades out]", "vocal fades out")
    if "和声" in value:
        return _Cue(f"[{section or 'Outro'} | background harmonies fade out]", "background harmonies fade out")
    if "画面" in value or "镜头" in value:
        return _Cue("[Visual Direction | camera pulls away]", "")
    if "重复副歌" in value:
        return _Cue("[Arrangement | repeat chorus]", "")
    return _Cue(f"[Instrumental {section or 'Outro'} | arrangement direction]", "arrangement direction")


def _augment_style_prompt(style_prompt: str, style_cues: list[str]) -> str:
    additions = [cue for cue in style_cues if cue and cue.lower() not in style_prompt.lower()]
    if not additions:
        return style_prompt
    return f"{style_prompt.strip().rstrip(',')}, {', '.join(additions)}"


def _validate_no_unsafe_suno_text(lyric_prompt: str) -> None:
    if re.search(r"^\s*(男|男声|女|女声|合|合唱|男女|男女合唱|男女交替)[：:]", lyric_prompt, flags=re.MULTILINE):
        raise ValueError("lyric_prompt contains Chinese vocal speaker prefixes after Suno postprocess")
    if re.search(r"^\s*[（(](男|男声|女|女声|合|合唱|男女|男女合唱|男女交替)[）)]", lyric_prompt, flags=re.MULTILINE):
        raise ValueError("lyric_prompt contains parenthesized Chinese vocal speaker prefixes after Suno postprocess")
    if re.search(r"^\s*[（(][^）)\n]*[\u4e00-\u9fff][^）)\n]*[）)]\s*$", lyric_prompt, flags=re.MULTILINE):
        raise ValueError("lyric_prompt contains Chinese parenthetical direction after Suno postprocess")
    if re.search(r"^\s*\[[^\]\n]*[\u4e00-\u9fff][^\]\n]*\]\s*$", lyric_prompt, flags=re.MULTILINE):
        raise ValueError("lyric_prompt contains Chinese bracket meta tag after Suno postprocess")


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    out = [str(item).strip() for item in value if str(item).strip()]
    if not out:
        raise ValueError(f"{label} must not be empty")
    return out


def _required_string(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    return text


def _is_markdown_separator(value: str) -> bool:
    return bool(re.fullmatch(r"[-_*=]{3,}", value))


def _has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


def _has_any(value: str, tokens: list[str]) -> bool:
    return any(token in value for token in tokens)


def _looks_like_lyric_sentence(value: str) -> bool:
    return _has_any(value, ["我", "你", "我们", "你们", "他们", "心", "梦", "爱", "路口", "背影"])
