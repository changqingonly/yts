"""创作 6 步 LangGraph 图(对应 tech.html 图5)。

analyze → structure → lyrics → build_style → final_draft → self_check
self_check 不满意时条件回边到 lyrics(Agent 化入口,有环图)。

节点本轮为 stub(产出占位),推理后端注入点已留(见 _NODES 注释 TODO):
真实实现处调 `backend.generate_text(...)`。checkpointer 由调用方注入
(本地 SqliteSaver / 云 PostgresSaver),保留断点续跑能力。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .state import CreationState

MAX_RETRIES = 1


def _stub(name: str, **patch):
    def node(state: CreationState) -> dict:
        stages = list(state.get("stages", []))
        # 轨迹仅记名;真实实现在此调 backend 推理
        from ..schemas.common import StageTrace

        stages.append(StageTrace(name=name, ok=True, note="stub"))
        return {**patch, "stages": stages}

    return node


def _self_check(state: CreationState) -> dict:
    from ..schemas.common import StageTrace

    stages = list(state.get("stages", []))
    stages.append(StageTrace(name="self_check", ok=True, note="stub-pass"))
    # TODO: 真实质量门(参考 creation-core quality.rs:150-300 可见字符等)
    return {"retry": False, "stages": stages}


def _route_after_check(state: CreationState) -> str:
    if state.get("retry") and state.get("retries", 0) < MAX_RETRIES:
        return "retry"
    return "done"


def build_creation_graph(*, checkpointer=None):
    g = StateGraph(CreationState)
    g.add_node("analyze", _stub("prompt_analyze", analysis="[stub] themes"))
    g.add_node("structure", _stub("make_structure", structure="[stub] verse/chorus"))
    g.add_node("lyrics", _stub("write_lyrics", lyrics="[stub] lyrics"))
    g.add_node("build_style", _stub("build_style", style="[stub] pop 120bpm"))
    g.add_node(
        "final_draft",
        _stub("generate_final_draft", final_draft="[stub] draft", title="[stub] title"),
    )
    g.add_node("self_check", _self_check)

    g.add_edge(START, "analyze")
    g.add_edge("analyze", "structure")
    g.add_edge("structure", "lyrics")
    g.add_edge("lyrics", "build_style")
    g.add_edge("build_style", "final_draft")
    g.add_edge("final_draft", "self_check")
    # self_check → 回炉 lyrics(Agent 化)或结束
    g.add_conditional_edges("self_check", _route_after_check, {"retry": "lyrics", "done": END})

    return g.compile(checkpointer=checkpointer)
