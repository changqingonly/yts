from __future__ import annotations

import json

import pytest
from yts_core.config import Settings
from yts_core.inference import make_backend


def test_make_backend_supports_explicit_pro_fixture() -> None:
    backend = make_backend(Settings(inference_backend="pro-fixture"))

    assert backend.name == "pro-fixture"


def test_make_backend_supports_explicit_openai_text_backend() -> None:
    backend = make_backend(
        Settings(
            inference_backend="openai",
            openai_api_key="sk-test",
            openai_text_model="gpt-4.1-mini",
        )
    )

    assert backend.name == "openai"


@pytest.mark.asyncio
async def test_pro_fixture_returns_stage_json() -> None:
    backend = make_backend(Settings(inference_backend="pro-fixture"))

    result = await backend.generate_text(
        [{"role": "user", "content": "YTS_PRO_STAGE: parse_intent\n{}"}]
    )

    payload = json.loads(result.text)
    assert payload["language"] == "zh"
    assert payload["genre"] == "Mandopop"
