from __future__ import annotations

import json

import pytest
from yts_core.config import Settings, get_settings
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


def test_make_backend_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unsupported inference backend"):
        make_backend(Settings(inference_backend="unknown"))


def test_get_settings_reads_explicit_config_file(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "openai.env"
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
    monkeypatch.setenv("YTS_CONFIG_FILE", str(config_file))

    settings = get_settings()

    assert settings.inference_backend == "openai"
    assert settings.openai_api_key == "sk-from-file"
    assert settings.openai_text_model == "gpt-4.1"


def test_get_settings_rejects_short_jwt_secret(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "short-secret.env"
    config_file.write_text("YTS_AUTH_JWT_SECRET=too-short\n", encoding="utf-8")
    monkeypatch.setenv("YTS_CONFIG_FILE", str(config_file))

    with pytest.raises(ValueError, match="auth_jwt_secret must be at least 32 bytes"):
        get_settings()


def test_get_settings_rejects_missing_explicit_config_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("YTS_CONFIG_FILE", str(tmp_path / "missing.env"))

    with pytest.raises(FileNotFoundError, match="YTS_CONFIG_FILE does not exist"):
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
