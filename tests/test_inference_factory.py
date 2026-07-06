from __future__ import annotations

import httpx
import pytest
from yts_core.config import Settings, get_settings
from yts_core.inference import make_backend
from yts_core.inference.cloud_adapter import CloudInference
from yts_core.inference.gateway_adapter import GatewayInference


def test_make_backend_maps_product_local_backend_to_candle() -> None:
    backend = make_backend(Settings(inference_backend="local"))

    assert isinstance(backend, GatewayInference)
    assert backend.name == "gateway"


def test_make_backend_maps_product_cloud_backend_to_cloud_inference() -> None:
    backend = make_backend(Settings(inference_backend="cloud"))

    assert isinstance(backend, CloudInference)
    assert backend.name == "cloud-litellm"


@pytest.mark.parametrize("backend", ["echo", "openai", "gateway", "pro-fixture", "unknown"])
def test_make_backend_rejects_unsupported_backend_values(backend: str) -> None:
    with pytest.raises(ValueError, match="Unsupported inference backend"):
        make_backend(Settings(inference_backend=backend))


def test_get_settings_reads_profile_config_file(monkeypatch, tmp_path) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    config_file = config_dir / "cloud.env"
    config_file.write_text(
        "\n".join(
            [
                "YTS_INFERENCE_BACKEND=cloud",
                "YTS_OPENAI_API_KEY=sk-from-file",
                "YTS_OPENAI_TEXT_MODEL=gpt-4.1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))

    settings = get_settings()

    assert settings.inference_backend == "cloud"
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
    backend = GatewayInference(
        Settings(
            gateway_base_url="http://127.0.0.1:9999",
            gateway_request_timeout_seconds=33,
            gateway_text_max_tokens=777,
        )
    )

    result = await backend.generate_text([{"role": "user", "content": "hello"}])

    assert result.text == "ok"
    assert observed["timeout"] == 33
    assert observed["url"] == "http://127.0.0.1:9999/text"
    assert observed["json"]["max_tokens"] == 777
