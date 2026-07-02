from __future__ import annotations

import pytest
from pydantic import SecretStr
from yts_core.config import Profile, Settings, get_settings, reload_settings


def test_settings_exposes_typed_config_sections() -> None:
    settings = Settings(
        profile="cloud",
        database_url="sqlite+aiosqlite:///typed.db",
        database_echo=True,
        inference_backend="openai",
        default_text_model="openai/gpt-4.1",
        model_fallbacks=["openai/gpt-4.1-mini", "anthropic/claude-sonnet-4"],
        deepseek_api_key="sk-deepseek",
        deepseek_text_model="deepseek/deepseek-chat",
        deepseek_base_url="https://api.deepseek.com/v1",
        openai_api_key="sk-typed",
        openai_text_model="gpt-4.1-mini",
        openai_image_model="gpt-image-1",
        openai_speech_model="gpt-4o-mini-tts",
        openai_base_url="https://api.example.test/v1",
        candle_base_url="http://127.0.0.1:8799",
        candle_text_max_tokens=1024,
        candle_request_timeout_seconds=45,
        image_provider="openai",
        image_model="gpt-image-1",
        audio_effect_provider="elevenlabs",
        audio_effect_model="sound-effects-v1",
        music_provider="suno",
        music_model="suno-v4.5",
        auth_jwt_secret="typed-secret-that-is-long-enough-for-hs256",
        auth_access_token_ttl_seconds=123,
        avatar_storage_dir="run/test-avatars",
        local_import_storage_dir="run/test-imports",
        billing_enabled=True,
        allow_custom_skills=False,
        phoenix_enabled=True,
        langgraph_checkpoint_backend="memory",
        langgraph_checkpoint_postgres_dsn="postgresql://example/checkpoints",
        logging_level="DEBUG",
        logging_format="json",
        server_allowed_origins=["http://127.0.0.1:1420", "https://studio.example.test"],
    )

    assert settings.database.url == "sqlite+aiosqlite:///typed.db"
    assert settings.database.echo is True
    assert settings.inference.backend == "openai"
    assert settings.inference.default_text_model == "openai/gpt-4.1"
    assert settings.inference.model_fallbacks == [
        "openai/gpt-4.1-mini",
        "anthropic/claude-sonnet-4",
    ]
    assert settings.deepseek.api_key == SecretStr("sk-deepseek")
    assert settings.deepseek.api_key_value == "sk-deepseek"
    assert settings.deepseek.text_model == "deepseek/deepseek-chat"
    assert settings.deepseek.base_url == "https://api.deepseek.com/v1"
    assert settings.openai.api_key == SecretStr("sk-typed")
    assert settings.openai.api_key_value == "sk-typed"
    assert settings.openai.text_model == "gpt-4.1-mini"
    assert settings.openai.image_model == "gpt-image-1"
    assert settings.openai.speech_model == "gpt-4o-mini-tts"
    assert settings.openai.base_url == "https://api.example.test/v1"
    assert settings.candle.base_url == "http://127.0.0.1:8799"
    assert settings.candle.text_max_tokens == 1024
    assert settings.candle.request_timeout_seconds == 45
    assert settings.image.provider == "openai"
    assert settings.image.model == "gpt-image-1"
    assert settings.audio_effect.provider == "elevenlabs"
    assert settings.audio_effect.model == "sound-effects-v1"
    assert settings.music.provider == "suno"
    assert settings.music.model == "suno-v4.5"
    assert settings.auth.jwt_secret_value == "typed-secret-that-is-long-enough-for-hs256"
    assert settings.auth.access_token_ttl_seconds == 123
    assert settings.storage.avatar_dir == "run/test-avatars"
    assert settings.storage.local_import_dir == "run/test-imports"
    assert settings.features.billing_enabled is True
    assert settings.features.allow_custom_skills is False
    assert settings.observability.phoenix_enabled is True
    assert settings.langgraph.checkpoint_backend == "memory"
    assert settings.langgraph.checkpoint_postgres_dsn == "postgresql://example/checkpoints"
    assert settings.logging.level == "DEBUG"
    assert settings.logging.format == "json"
    assert settings.server.allowed_origins == [
        "http://127.0.0.1:1420",
        "https://studio.example.test",
    ]

    assert settings.openai_api_key == "sk-typed"
    assert settings.deepseek_api_key == "sk-deepseek"
    assert settings.deepseek_text_model == "deepseek/deepseek-chat"
    assert settings.deepseek_base_url == "https://api.deepseek.com/v1"
    assert settings.auth_jwt_secret == "typed-secret-that-is-long-enough-for-hs256"
    assert settings.database_echo is True
    assert settings.image_provider == "openai"
    assert settings.image_model == "gpt-image-1"
    assert settings.audio_effect_provider == "elevenlabs"
    assert settings.audio_effect_model == "sound-effects-v1"
    assert settings.music_provider == "suno"
    assert settings.music_model == "suno-v4.5"
    assert settings.logging_level == "DEBUG"
    assert settings.server_allowed_origins == [
        "http://127.0.0.1:1420",
        "https://studio.example.test",
    ]


def test_get_settings_is_cached_until_reloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YTS_INFERENCE_BACKEND", "echo")
    reload_settings()

    first = get_settings()
    monkeypatch.setenv("YTS_INFERENCE_BACKEND", "openai")
    second = get_settings()

    assert second is first
    assert second.inference_backend == "echo"

    reloaded = reload_settings()

    assert reloaded is get_settings()
    assert reloaded.inference_backend == "openai"


def test_settings_reads_profile_config_file_and_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    config_file = config_dir / "cloud.env"
    config_file.write_text(
        "\n".join(
            [
                "YTS_INFERENCE_BACKEND=echo",
                "YTS_DEFAULT_TEXT_MODEL=deepseek/deepseek-chat",
                "YTS_DEEPSEEK_API_KEY=sk-deepseek-file",
                "YTS_DEEPSEEK_TEXT_MODEL=deepseek/deepseek-chat",
                "YTS_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1",
                "YTS_OPENAI_API_KEY=sk-from-file",
                "YTS_OPENAI_TEXT_MODEL=gpt-4.1",
                "YTS_DATABASE_ECHO=true",
                "YTS_LOGGING_LEVEL=DEBUG",
                "YTS_LOGGING_FORMAT=json",
                'YTS_SERVER_ALLOWED_ORIGINS=["http://127.0.0.1:1420","https://studio.example.test"]',
                "YTS_CANDLE_TEXT_MAX_TOKENS=512",
                "YTS_IMAGE_PROVIDER=openai",
                "YTS_IMAGE_MODEL=gpt-image-1",
                "YTS_AUDIO_EFFECT_PROVIDER=elevenlabs",
                "YTS_AUDIO_EFFECT_MODEL=sound-effects-v1",
                "YTS_MUSIC_PROVIDER=suno",
                "YTS_MUSIC_MODEL=suno-v4.5",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("YTS_OPENAI_TEXT_MODEL", "gpt-4.1-mini")

    settings = reload_settings()

    assert settings.inference_backend == "echo"
    assert settings.default_text_model == "deepseek/deepseek-chat"
    assert settings.deepseek_api_key == "sk-deepseek-file"
    assert settings.deepseek_text_model == "deepseek/deepseek-chat"
    assert settings.deepseek_base_url == "https://api.deepseek.com/v1"
    assert settings.openai_api_key == "sk-from-file"
    assert settings.openai.text_model == "gpt-4.1-mini"
    assert settings.database.echo is True
    assert settings.logging.level == "DEBUG"
    assert settings.logging.format == "json"
    assert settings.server.allowed_origins == [
        "http://127.0.0.1:1420",
        "https://studio.example.test",
    ]
    assert settings.candle.text_max_tokens == 512
    assert settings.image.provider == "openai"
    assert settings.image.model == "gpt-image-1"
    assert settings.audio_effect.provider == "elevenlabs"
    assert settings.audio_effect.model == "sound-effects-v1"
    assert settings.music.provider == "suno"
    assert settings.music.model == "suno-v4.5"


def test_local_profile_settings_are_explicit_overrides() -> None:
    settings = Settings.for_profile(Profile.LOCAL)

    assert settings.profile == Profile.LOCAL
    assert settings.database.url == "sqlite+aiosqlite:///./yts_local.db"
    assert settings.inference.backend == "openai"
    assert settings.features.allow_custom_skills is True
    assert settings.features.billing_enabled is False
    assert settings.observability.phoenix_enabled is False


def test_cloud_profile_settings_are_explicit_overrides() -> None:
    settings = Settings.for_profile(Profile.CLOUD)

    assert settings.profile == Profile.CLOUD
    assert settings.database.url == "postgresql+asyncpg://localhost/yts"
    assert settings.inference.backend == "echo"
    assert settings.features.allow_custom_skills is False
    assert settings.features.billing_enabled is True


def test_get_settings_applies_local_profile_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    monkeypatch.setenv("YTS_PROFILE", "local")
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))

    settings = reload_settings()

    assert settings.profile == Profile.LOCAL
    assert settings.database.url == "sqlite+aiosqlite:///./yts_local.db"
    assert settings.inference.backend == "openai"
    assert settings.features.allow_custom_skills is True
    assert settings.features.billing_enabled is False


def test_get_settings_reads_default_local_profile_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    local_file = config_dir / "local.env"
    local_file.write_text(
        "\n".join(
            [
                "YTS_OPENAI_API_KEY=sk-local-file",
                "YTS_OPENAI_TEXT_MODEL=gpt-local-file",
                "YTS_INFERENCE_BACKEND=pro-fixture",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("YTS_PROFILE", "local")
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))

    settings = reload_settings()

    assert settings.profile == Profile.LOCAL
    assert settings.openai_api_key == "sk-local-file"
    assert settings.openai_text_model == "gpt-local-file"
    assert settings.inference_backend == "pro-fixture"


def test_get_settings_rejects_unknown_profile_config_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YTS_CONFIG_DIR", "/path/that/does/not/exist")

    with pytest.raises(FileNotFoundError, match="YTS_CONFIG_DIR does not exist"):
        reload_settings()


@pytest.mark.parametrize("removed_name", ["YTS_CONFIG_FILE", "YTS_CONFIG_HOME"])
def test_get_settings_rejects_removed_config_knobs(
    monkeypatch: pytest.MonkeyPatch, removed_name: str
) -> None:
    monkeypatch.setenv(removed_name, "/tmp/legacy-yts-config")

    with pytest.raises(ValueError, match=f"{removed_name} is no longer supported"):
        reload_settings()
