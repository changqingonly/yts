"""Pro creation graph factory."""

from __future__ import annotations

from .flow_builder import build_flow_graph
from .flows.pro_lyrics import PRO_FLOW_SPEC, PRO_STAGE_ORDER
from .nodes.pro_lyrics import ProLyricsNodes


def build_creation_graph(*, backend, checkpointer=None):
    """Build and compile the Pro lyrics creation graph."""

    return build_flow_graph(
        PRO_FLOW_SPEC,
        ProLyricsNodes(backend),
        checkpointer=checkpointer,
    )


__all__ = ["PRO_STAGE_ORDER", "build_creation_graph"]
