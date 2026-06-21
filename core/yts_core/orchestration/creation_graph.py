"""创作 6 步 LangGraph 图(对应 tech.html 图5)。

analyze → structure → lyrics → build_style → final_draft → self_check
self_check 不通过时条件回边到 lyrics(Agent 化入口,有环图)。

节点真实调用注入的推理后端(InferenceBackend);后端由调用方按配置选择
(echo / cloud / candle,见 inference.make_backend)。checkpointer 由调用方注入
(本地 SqliteSaver / 云 PostgresSaver),保留断点续跑能力。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..schemas.common import StageTrace
from .state import CreationState

MAX_RETRIES = 1


def _append_stage(
    state: CreationState, name: str, provider: str, ok: bool = True
) -> list[StageTrace]:
    stages = list(state.get("stages", []))
    stages.append(StageTrace(name=name, ok=ok, note=provider))
    return stages


def build_creation_graph(*, backend, checkpointer=None):
    """构建并编译创作图。backend 必传(实现 InferenceBackend.generate_text)。"""

    async def analyze(state: CreationState) -> dict:
        r = await backend.generate_text(
            [{"role": "user", "content": f"提取这段创作需求的主题与情绪:\n{state['user_prompt']}"}]
        )
        return {"analysis": r.text, "stages": _append_stage(state, "prompt_analyze", r.provider)}

    async def structure(state: CreationState) -> dict:
        r = await backend.generate_text(
            [
                {
                    "role": "user",
                    "content": f"根据主题给出歌曲段落结构(主歌/副歌/桥段):\n{state.get('analysis', '')}",
                }
            ]
        )
        return {"structure": r.text, "stages": _append_stage(state, "make_structure", r.provider)}

    async def write_lyrics(state: CreationState) -> dict:
        r = await backend.generate_text(
            [
                {
                    "role": "user",
                    "content": (
                        "按以下结构与主题写歌词:\n"
                        f"结构:{state.get('structure', '')}\n主题:{state.get('analysis', '')}"
                    ),
                }
            ]
        )
        return {"lyrics": r.text, "stages": _append_stage(state, "write_lyrics", r.provider)}

    async def build_style(state: CreationState) -> dict:
        r = await backend.generate_text(
            [
                {
                    "role": "user",
                    "content": f"给出曲风、编制与 BPM 建议:\n{state.get('analysis', '')}",
                }
            ]
        )
        return {"style": r.text, "stages": _append_stage(state, "build_style", r.provider)}

    async def final_draft(state: CreationState) -> dict:
        r = await backend.generate_text(
            [{"role": "user", "content": f"把歌词整合为成稿:\n{state.get('lyrics', '')}"}]
        )
        title = (state.get("analysis", "") or "untitled").strip().splitlines()[0][:16]
        return {
            "final_draft": r.text,
            "title": title,
            "stages": _append_stage(state, "generate_final_draft", r.provider),
        }

    def self_check(state: CreationState) -> dict:
        # 质量门(stub):歌词非空即通过。TODO: 可见字符 150–300 等(参考 creation-core quality.rs)
        ok = len(state.get("lyrics", "").strip()) > 0
        return {
            "retry": not ok,
            "stages": _append_stage(state, "self_check", "gate", ok=ok),
        }

    def route_after_check(state: CreationState) -> str:
        if state.get("retry") and state.get("retries", 0) < MAX_RETRIES:
            return "retry"
        return "done"

    g = StateGraph(CreationState)
    g.add_node("analyze", analyze)
    g.add_node("structure", structure)
    g.add_node("lyrics", write_lyrics)
    g.add_node("build_style", build_style)
    g.add_node("final_draft", final_draft)
    g.add_node("self_check", self_check)

    g.add_edge(START, "analyze")
    g.add_edge("analyze", "structure")
    g.add_edge("structure", "lyrics")
    g.add_edge("lyrics", "build_style")
    g.add_edge("build_style", "final_draft")
    g.add_edge("final_draft", "self_check")
    g.add_conditional_edges("self_check", route_after_check, {"retry": "lyrics", "done": END})

    return g.compile(checkpointer=checkpointer)
