from __future__ import annotations

import json

import httpx
import pytest
from yts_core.config import Settings, get_settings
from yts_core.inference import make_backend
from yts_core.inference.candle_adapter import CandleInference


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


def test_make_backend_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unsupported inference backend"):
        make_backend(Settings(inference_backend="unknown"))


def test_get_settings_reads_profile_config_file(monkeypatch, tmp_path) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    config_file = config_dir / "cloud.env"
    config_file.write_text(
        "\n".join(
            [
                "YTS_INFERENCE_BACKEND=openai",
                "YTS_OPENAI_API_KEY=sk-from-file",
                "YTS_OPENAI_TEXT_MODEL=gpt-4.1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))

    settings = get_settings()

    assert settings.inference_backend == "openai"
    assert settings.openai_api_key == "sk-from-file"
    assert settings.openai_text_model == "gpt-4.1"


def test_get_settings_rejects_short_jwt_secret(monkeypatch, tmp_path) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    config_file = config_dir / "cloud.env"
    config_file.write_text("YTS_AUTH_JWT_SECRET=too-short\n", encoding="utf-8")
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))

    with pytest.raises(ValueError, match="auth_jwt_secret must be at least 32 bytes"):
        get_settings()


def test_get_settings_rejects_missing_config_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("YTS_CONFIG_DIR", str(tmp_path / "missing-conf"))

    with pytest.raises(FileNotFoundError, match="YTS_CONFIG_DIR does not exist"):
        get_settings()


@pytest.mark.asyncio
async def test_pro_fixture_returns_stage_json() -> None:
    backend = make_backend(Settings(inference_backend="pro-fixture"))

    result = await backend.generate_text(
        [{"role": "user", "content": "YTS_PRO_STAGE: parse_intent\n{}"}]
    )

    payload = json.loads(result.text)
    assert payload["language"] == "zh"
    assert payload["genre"] == "Mandopop"


@pytest.mark.asyncio
async def test_candle_inference_uses_configured_timeout_and_text_max_tokens(monkeypatch) -> None:
    observed = {}

    class FakeClient:
        def __init__(self, *, timeout):
            observed["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, json):
            observed["url"] = url
            observed["json"] = json
            return httpx.Response(
                200,
                json={"text": "ok", "model": "tinyllama"},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    backend = CandleInference(
        Settings(
            candle_base_url="http://127.0.0.1:9999",
            candle_request_timeout_seconds=33,
            candle_text_max_tokens=777,
        )
    )

    result = await backend.generate_text([{"role": "user", "content": "hello"}])

    assert result.text == "ok"
    assert observed["timeout"] == 33
    assert observed["url"] == "http://127.0.0.1:9999/candle/text"
    assert observed["json"]["max_tokens"] == 777
