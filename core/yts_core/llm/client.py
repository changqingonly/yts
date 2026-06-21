"""LiteLLM 调用封装。云实现用;桌面本地实现走 Candle(见 inference/candle_adapter)。

出站调用在桌面端须经 Rust 出口代理(认证/拦截/审计)——把 base_url 指向本地代理即可。
"""

from __future__ import annotations

from ..config import get_settings
from ..inference.port import TextResult


async def complete_text(
    messages: list[dict],
    *,
    model: str | None = None,
    fallbacks: list[str] | None = None,
) -> TextResult:
    settings = get_settings()
    model = model or settings.default_text_model
    fallbacks = fallbacks if fallbacks is not None else settings.model_fallbacks

    # 延迟 import,避免 core 仅做 schema 时强依赖 litellm
    import litellm

    resp = await litellm.acompletion(
        model=model,
        messages=messages,
        fallbacks=fallbacks,
    )
    text = resp["choices"][0]["message"]["content"]
    used = resp.get("model", model)
    return TextResult(text=text, provider=used.split("/")[0], model=used)
