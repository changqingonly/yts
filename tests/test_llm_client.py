from __future__ import annotations

import sys
import types

import pytest
from yts_core.config import Settings
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
    assert observed["base_url"] == "https://api.openai.example/v1"
    assert observed["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_complete_openai_text_fails_when_api_key_is_missing() -> None:
    with pytest.raises(ValueError, match="openai_api_key must be configured"):
        await complete_openai_text(
            [{"role": "user", "content": "hello"}],
            settings=Settings(openai_api_key=""),
        )
