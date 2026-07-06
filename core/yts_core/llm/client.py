"""
LiteLLM 调用封装。云实现用;桌面本地实现走 GGML 网关(见 inference/gateway_adapter)
出站调用在桌面端须经 Rust 出口代理(认证/拦截/审计)——把 base_url 指向本地代理即可
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from threading import Lock, Thread
from time import perf_counter
from typing import Any

import structlog

from ..config import Settings, get_settings
from ..inference.port import TextResult

logger = structlog.get_logger(__name__)

_LITELLM_LOOP_LOCK = Lock()
_LITELLM_LOOP: asyncio.AbstractEventLoop | None = None
_LITELLM_LOOP_THREAD: Thread | None = None


async def complete_text(
    messages: list[dict],
    *,
    settings: Settings | None = None,
    model: str | None = None,
    fallbacks: list[str] | None = None,
    response_format: dict | None = None,
) -> TextResult:
    settings = settings or get_settings()
    model = model or settings.default_text_model
    fallbacks = fallbacks if fallbacks is not None else settings.model_fallbacks

    # 延迟 import,避免 core 仅做 schema 时强依赖 litellm
    import litellm

    started_at = perf_counter()
    logger.info(
        "llm.litellm.requested",
        model=model,
        fallback_count=len(fallbacks or []),
        message_count=len(messages),
        response_format=bool(response_format),
    )
    kwargs = {
        "model": model,
        "messages": messages,
        "fallbacks": fallbacks,
        "response_format": response_format,
    }
    kwargs.update(_provider_kwargs(model, settings))
    try:
        resp = await _run_litellm_acompletion(
            litellm,
            kwargs,
        )
    except Exception as exc:
        duration_ms = _elapsed_ms(started_at)
        logger.exception(
            "llm.litellm.failed",
            model=model,
            error_type=type(exc).__name__,
            duration_ms=duration_ms,
        )
        if _is_openai_compatible_model(model):
            _raise_openai_text_error(
                exc,
                base_url=settings.openai_base_url.strip(),
                model=model,
            )
        raise
    text = resp["choices"][0]["message"]["content"]
    used = resp.get("model", model)
    provider = _provider_name(used)
    duration_ms = _elapsed_ms(started_at)
    logger.info(
        "llm.litellm.completed",
        model=used,
        provider=provider,
        response_chars=len(text),
        duration_ms=duration_ms,
    )
    return TextResult(text=text, provider=provider, model=used)


def _provider_kwargs(model: str, settings: Settings) -> dict[str, Any]:
    if _is_deepseek_model(model):
        api_key = settings.deepseek_api_key.strip()
        if not api_key:
            raise ValueError("deepseek_api_key must be configured for DeepSeek text inference")
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "custom_llm_provider": "deepseek",
            "timeout": settings.deepseek_request_timeout_seconds,
            "max_retries": settings.deepseek_max_retries,
        }
        base_url = settings.deepseek_base_url.strip()
        if base_url:
            kwargs["base_url"] = base_url
        return kwargs
    if _is_openai_compatible_model(model):
        api_key = settings.openai_api_key.strip()
        if not api_key:
            raise ValueError("openai_api_key must be configured for OpenAI text inference")
        kwargs = {
            "api_key": api_key,
            "custom_llm_provider": "openai",
            "timeout": settings.openai_request_timeout_seconds,
            "max_retries": settings.openai_max_retries,
        }
        base_url = settings.openai_base_url.strip()
        if base_url:
            kwargs["base_url"] = base_url
        return kwargs
    return {}


def _is_deepseek_model(model: str) -> bool:
    return model.startswith("deepseek/") or model.startswith("deepseek-")


def _is_openai_compatible_model(model: str) -> bool:
    return model.startswith("openai/") or model.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4"))


def _provider_name(model: str) -> str:
    if _is_deepseek_model(model):
        return "deepseek"
    if _is_openai_compatible_model(model):
        return "openai"
    return model.split("/")[0]


async def _run_litellm_acompletion(litellm_module, kwargs: dict[str, Any]):
    loop = _litellm_event_loop()
    future = asyncio.run_coroutine_threadsafe(
        litellm_module.acompletion(**kwargs),
        loop,
    )
    return await asyncio.wrap_future(future)


def _litellm_event_loop() -> asyncio.AbstractEventLoop:
    global _LITELLM_LOOP, _LITELLM_LOOP_THREAD

    with _LITELLM_LOOP_LOCK:
        if (
            _LITELLM_LOOP is not None
            and _LITELLM_LOOP_THREAD is not None
            and _LITELLM_LOOP_THREAD.is_alive()
            and not _LITELLM_LOOP.is_closed()
        ):
            return _LITELLM_LOOP

        loop_ready: Future[asyncio.AbstractEventLoop] = Future()

        def run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_ready.set_result(loop)
            loop.run_forever()

        thread = Thread(target=run_loop, name="yts-litellm-loop", daemon=True)
        thread.start()
        _LITELLM_LOOP = loop_ready.result()
        _LITELLM_LOOP_THREAD = thread
        return _LITELLM_LOOP


def _raise_openai_text_error(exc: Exception, *, base_url: str, model: str) -> None:
    message = str(exc)
    hint = ""
    if _looks_like_html_gateway_response(message):
        if _looks_like_gateway_timeout(message):
            hint = "; upstream OpenAI-compatible gateway returned HTML 504 Gateway Time-out"
        elif not _looks_like_timeout(exc, message):
            hint = (
                "; endpoint returned HTML instead of JSON. For OpenAI-compatible gateways, "
                "set YTS_OPENAI_BASE_URL to the API root, usually ending in /v1, not the web UI root"
            )
    raise ValueError(
        f"OpenAI text inference failed: {type(exc).__name__}: base_url={base_url or '<default>'} "
        f"model={model}{hint}"
    ) from exc


def _looks_like_html_gateway_response(message: str) -> bool:
    lowered = message.lower()
    return "<!doctype html" in lowered or "<html" in lowered


def _looks_like_timeout(exc: Exception, message: str) -> bool:
    name = type(exc).__name__.lower()
    lowered = message.lower()
    return "timeout" in name or "timed out" in lowered


def _looks_like_gateway_timeout(message: str) -> bool:
    lowered = message.lower()
    return "504 gateway time-out" in lowered or "504 gateway timeout" in lowered


def _elapsed_ms(started_at: float) -> int:
    return max(0, int(round((perf_counter() - started_at) * 1000)))
