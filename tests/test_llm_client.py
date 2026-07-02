from __future__ import annotations

import asyncio
import sys
import types

import httpx
import pytest
from yts_core.config import Settings, reload_settings
from yts_core.llm.client import complete_openai_text, complete_text


@pytest.mark.asyncio
async def test_complete_text_passes_response_format_to_litellm(monkeypatch) -> None:
    observed = {}
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**kwargs):
        observed.update(kwargs)
        return {"choices": [{"message": {"content": "{}"}}], "model": kwargs["model"]}

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)

    result = await complete_text(
        [{"role": "user", "content": "return json"}],
        model="fake/model",
        fallbacks=[],
        response_format={"type": "json_object"},
    )

    assert result.text == "{}"
    assert observed["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_complete_text_passes_deepseek_config_to_litellm(monkeypatch) -> None:
    observed = {}
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**kwargs):
        observed.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}], "model": kwargs["model"]}

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)
    monkeypatch.setenv("YTS_DEFAULT_TEXT_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("YTS_DEEPSEEK_API_KEY", "sk-deepseek-configured")
    monkeypatch.setenv("YTS_DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("YTS_DEEPSEEK_REQUEST_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("YTS_DEEPSEEK_MAX_RETRIES", "1")

    result = await complete_text([{"role": "user", "content": "hello"}])

    assert result.text == "ok"
    assert result.provider == "deepseek"
    assert observed["model"] == "deepseek/deepseek-chat"
    assert observed["api_key"] == "sk-deepseek-configured"
    assert observed["base_url"] == "https://api.deepseek.com/v1"
    assert observed["timeout"] == 90
    assert observed["max_retries"] == 1
    reload_settings()


@pytest.mark.asyncio
async def test_complete_text_routes_deepseek_v4_model_to_deepseek_provider(monkeypatch) -> None:
    observed = {}
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**kwargs):
        observed.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}], "model": kwargs["model"]}

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)
    monkeypatch.setenv("YTS_DEFAULT_TEXT_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("YTS_DEEPSEEK_API_KEY", "sk-deepseek-v4")
    monkeypatch.setenv("YTS_DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    result = await complete_text([{"role": "user", "content": "hello"}])

    assert result.text == "ok"
    assert result.provider == "deepseek"
    assert observed["model"] == "deepseek-v4-pro"
    assert observed["custom_llm_provider"] == "deepseek"
    assert observed["api_key"] == "sk-deepseek-v4"
    assert observed["base_url"] == "https://api.deepseek.com/v1"
    reload_settings()


@pytest.mark.asyncio
async def test_complete_openai_text_passes_configured_key_base_url_and_model(monkeypatch) -> None:
    observed = {}
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**kwargs):
        observed.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}], "model": kwargs["model"]}

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)

    result = await complete_openai_text(
        [{"role": "user", "content": "hello"}],
        settings=Settings(
            openai_api_key="sk-configured",
            openai_text_model="gpt-4.1-mini",
            openai_base_url="https://api.openai.example/v1",
        ),
        response_format={"type": "json_object"},
    )

    assert result.text == "ok"
    assert result.provider == "openai"
    assert result.model == "gpt-4.1-mini"
    assert observed["model"] == "gpt-4.1-mini"
    assert observed["api_key"] == "sk-configured"
    assert observed["custom_llm_provider"] == "openai"
    assert observed["base_url"] == "https://api.openai.example/v1"
    assert observed["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_litellm_preserves_base_url_domain_port(monkeypatch) -> None:
    import litellm

    observed_urls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed_urls.append(request.url)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "id": "chatcmpl-port-test",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-5.5",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(litellm, "aclient_session", client)
    try:
        await litellm.acompletion(
            model="gpt-5.5",
            messages=[{"role": "user", "content": "hello"}],
            api_key="sk-port-test",
            base_url="https://api.example.test:8088/v1",
            custom_llm_provider="openai",
            timeout=30,
        )
    finally:
        await client.aclose()
        monkeypatch.setattr(litellm, "aclient_session", None)

    assert [str(url) for url in observed_urls] == [
        "https://api.example.test:8088/v1/chat/completions"
    ]
    assert observed_urls[0].host == "api.example.test"
    assert observed_urls[0].port == 8088


@pytest.mark.asyncio
async def test_complete_openai_text_reuses_shared_litellm_event_loop(monkeypatch) -> None:
    loops = []
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**kwargs):
        loops.append(asyncio.get_running_loop())
        return {"choices": [{"message": {"content": "ok"}}], "model": kwargs["model"]}

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)
    settings = Settings(
        openai_api_key="sk-configured",
        openai_text_model="gpt-4.1-mini",
        openai_base_url="https://api.openai.example/v1",
    )

    await complete_openai_text([{"role": "user", "content": "hello"}], settings=settings)
    await complete_openai_text([{"role": "user", "content": "again"}], settings=settings)

    assert len(loops) == 2
    assert loops[0] is loops[1]
    assert loops[0] is not asyncio.get_running_loop()
    assert not loops[0].is_closed()


@pytest.mark.asyncio
async def test_complete_openai_text_fails_when_api_key_is_missing() -> None:
    with pytest.raises(ValueError, match="openai_api_key must be configured"):
        await complete_openai_text(
            [{"role": "user", "content": "hello"}],
            settings=Settings(openai_api_key=""),
        )


@pytest.mark.asyncio
async def test_complete_openai_text_rewrites_html_gateway_response_error(monkeypatch) -> None:
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**_kwargs):
        raise RuntimeError(
            "OpenAIException - Empty or invalid response from LLM endpoint. "
            "Received: '<!doctype html><html><title>Sub2API - AI API Gateway</title></html>'"
        )

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)

    with pytest.raises(ValueError) as exc_info:
        await complete_openai_text(
            [{"role": "user", "content": "hello"}],
            settings=Settings(
                openai_api_key="sk-configured",
                openai_text_model="gpt-4.1-mini",
                openai_base_url="https://api.example.test",
            ),
        )

    message = str(exc_info.value)
    assert "OpenAI text inference failed" in message
    assert "base_url=https://api.example.test" in message
    assert "model=gpt-4.1-mini" in message
    assert "returned HTML instead of JSON" in message
    assert "/v1" in message
    assert "sk-configured" not in message


@pytest.mark.asyncio
async def test_complete_openai_text_timeout_error_does_not_claim_html_gateway(monkeypatch) -> None:
    litellm = types.ModuleType("litellm")

    class Timeout(Exception):
        pass

    async def fake_acompletion(**_kwargs):
        raise Timeout("request timed out after receiving <!doctype html><html></html>")

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)

    with pytest.raises(ValueError) as exc_info:
        await complete_openai_text(
            [{"role": "user", "content": "hello"}],
            settings=Settings(
                openai_api_key="sk-configured",
                openai_text_model="gpt-5.5",
                openai_base_url="https://api.example.test/v1",
            ),
        )

    message = str(exc_info.value)
    assert "Timeout" in message
    assert "returned HTML instead of JSON" not in message
    assert "not the web UI root" not in message


@pytest.mark.asyncio
async def test_complete_openai_text_reports_html_gateway_timeout(monkeypatch) -> None:
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**_kwargs):
        raise RuntimeError(
            "<html><head><title>504 Gateway Time-out</title></head>"
            "<body><center><h1>504 Gateway Time-out</h1></center></body></html>"
        )

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)

    with pytest.raises(ValueError) as exc_info:
        await complete_openai_text(
            [{"role": "user", "content": "hello"}],
            settings=Settings(
                openai_api_key="sk-configured",
                openai_text_model="gpt-5.5",
                openai_base_url="https://api.example.test:8088/v1",
            ),
        )

    message = str(exc_info.value)
    assert "upstream OpenAI-compatible gateway returned HTML 504 Gateway Time-out" in message
    assert "not the web UI root" not in message


@pytest.mark.asyncio
async def test_complete_openai_text_passes_configured_timeout(monkeypatch) -> None:
    observed = {}
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**kwargs):
        observed.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}], "model": kwargs["model"]}

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)

    await complete_openai_text(
        [{"role": "user", "content": "hello"}],
        settings=Settings(
            openai_api_key="sk-configured",
            openai_text_model="gpt-5.5",
            openai_base_url="https://api.example.test/v1",
            openai_request_timeout_seconds=180,
        ),
    )

    assert observed["timeout"] == 180


@pytest.mark.asyncio
async def test_complete_openai_text_disables_openai_sdk_retries_by_default(monkeypatch) -> None:
    observed = {}
    litellm = types.ModuleType("litellm")

    async def fake_acompletion(**kwargs):
        observed.update(kwargs)
        return {"choices": [{"message": {"content": "ok"}}], "model": kwargs["model"]}

    litellm.acompletion = fake_acompletion
    monkeypatch.setitem(sys.modules, "litellm", litellm)

    await complete_openai_text(
        [{"role": "user", "content": "hello"}],
        settings=Settings(
            openai_api_key="sk-configured",
            openai_text_model="gpt-5.5",
            openai_base_url="https://api.example.test:8088/v1",
        ),
    )

    assert observed["max_retries"] == 0
