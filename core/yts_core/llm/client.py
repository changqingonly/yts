"""
LiteLLM 调用封装。云实现用;桌面本地实现走 Candle(见 inference/candle_adapter)
出站调用在桌面端须经 Rust 出口代理(认证/拦截/审计)——把 base_url 指向本地代理即可
"""

from __future__ import annotations

from ..config import Settings, get_settings
from ..inference.port import TextResult


async def complete_text(
    messages: list[dict],
    *,
    model: str | None = None,
    fallbacks: list[str] | None = None,
    response_format: dict | None = None,
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
        response_format=response_format,
    )
    text = resp["choices"][0]["message"]["content"]
    used = resp.get("model", model)
    return TextResult(text=text, provider=used.split("/")[0], model=used)


async def complete_openai_text(
    messages: list[dict],
    *,
    settings: Settings | None = None,
    model: str | None = None,
    response_format: dict | None = None,
) -> TextResult:
    settings = settings or get_settings()
    api_key = settings.openai_api_key.strip()
    if not api_key:
        raise ValueError("openai_api_key must be configured for OpenAI text inference")
    selected_model = model or settings.openai_text_model.strip()
    if not selected_model:
        raise ValueError("openai_text_model must be configured for OpenAI text inference")

    import litellm

    kwargs = {
        "model": selected_model,
        "messages": messages,
        "api_key": api_key,
        "response_format": response_format,
    }
    base_url = settings.openai_base_url.strip()
    if base_url:
        kwargs["base_url"] = base_url
    resp = await litellm.acompletion(**kwargs)
    text = resp["choices"][0]["message"]["content"]
    used = resp.get("model", selected_model)
    return TextResult(text=text, provider="openai", model=used)
