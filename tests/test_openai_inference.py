from __future__ import annotations

import pytest
from yts_core.config import Settings
from yts_core.inference.openai_adapter import OpenAIInference
from yts_core.inference.port import TextResult


@pytest.mark.asyncio
async def test_openai_inference_uses_openai_text_client(monkeypatch) -> None:
    observed = {}

    async def fake_complete_openai_text(messages, *, settings, model=None, response_format=None):
        observed.update(
            {
                "messages": messages,
                "settings": settings,
                "model": model,
                "response_format": response_format,
            }
        )
        return TextResult(text="{}", provider="openai", model=model or settings.openai_text_model)

    monkeypatch.setattr(
        "yts_core.inference.openai_adapter.complete_openai_text",
        fake_complete_openai_text,
    )
    settings = Settings(openai_api_key="sk-test", openai_text_model="gpt-4.1-mini")
    backend = OpenAIInference(settings)

    result = await backend.generate_text(
        [{"role": "user", "content": "json"}],
        model="gpt-4.1",
        response_format={"type": "json_object"},
    )

    assert result.provider == "openai"
    assert result.model == "gpt-4.1"
    assert observed["settings"] is settings
    assert observed["model"] == "gpt-4.1"
    assert observed["response_format"] == {"type": "json_object"}
