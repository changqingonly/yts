from __future__ import annotations

from langgraph.graph import END, START

from ..flow_builder import FlowSpec
from ..state import CreationState

PRO_STAGE_ORDER = (
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
)

PRO_FLOW_EDGES = (
    (START, "validate_request"),
    ("validate_request", "parse_intent"),
    ("parse_intent", "build_song_brief"),
    ("build_song_brief", "plan_music_style"),
    ("plan_music_style", "hook_lab"),
    ("hook_lab", "draft_structure_blueprints"),
    ("draft_structure_blueprints", "critique_structure"),
    ("critique_structure", "plan_style_prompt"),
    ("plan_style_prompt", "generate_lyrics"),
    ("generate_lyrics", "review_quality"),
    ("review_quality", "repair_lyrics"),
    ("repair_lyrics", "normalize_suno_format"),
    ("normalize_suno_format", "refine_title"),
    ("refine_title", "build_response"),
    ("build_response", END),
)

PRO_FLOW_SPEC = FlowSpec(
    name="pro_lyrics",
    state_type=CreationState,
    stages=PRO_STAGE_ORDER,
    edges=PRO_FLOW_EDGES,
)

__all__ = ["PRO_FLOW_EDGES", "PRO_FLOW_SPEC", "PRO_STAGE_ORDER"]
