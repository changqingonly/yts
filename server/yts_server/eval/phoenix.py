"""
Phoenix 初始化(可开关,YTS_PHOENIX_ENABLED)。

追踪 LangGraph 每个节点 + LiteLLM 调用;离线评估/数据集回放 TODO。
"""

from __future__ import annotations


def init_phoenix() -> None:
    import phoenix as px
    from openinference.instrumentation.langchain import LangChainInstrumentor

    px.launch_app()  # 本地 Phoenix UI;生产可改 collector endpoint
    LangChainInstrumentor().instrument()
    print("[phoenix] tracing enabled (LangChain/LangGraph)")
    # TODO: 评估数据集 / LLM-as-judge 回放
