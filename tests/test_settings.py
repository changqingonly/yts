from __future__ import annotations

from pathlib import Path

import pytest
import yts_core.config as config
from pydantic import SecretStr, ValidationError
from yts_core.config import Profile, Settings, get_settings, reload_settings

_TEST_JWT_SECRET = "test-secret-that-is-long-enough-for-hs256"


def _write_strict_profile(
    config_dir: Path,
    profile: Profile,
    *,
    overrides: dict[str, str] | None = None,
    omitted: set[str] | None = None,
) -> Path:
    values = {
        "YTS_PROFILE": profile.value,
        "YTS_DATABASE_URL": "sqlite+aiosqlite:///./test.db",
        "YTS_INFERENCE_BACKEND": profile.value,
        "YTS_AUTH_JWT_SECRET": _TEST_JWT_SECRET,
        "YTS_LANGGRAPH_CHECKPOINT_BACKEND": "memory",
    }
    if profile == Profile.LOCAL:
        values["YTS_GATEWAY_BASE_URL"] = "http://127.0.0.1:8799"
    else:
        values.update(
            {
                "YTS_DEFAULT_TEXT_MODEL": "deepseek/deepseek-chat",
                "YTS_DEEPSEEK_API_KEY": "sk-deepseek-test",
                "YTS_OPENAI_API_KEY": "sk-openai-test",
            }
        )
    values.update(overrides or {})
    for name in omitted or set():
        values.pop(name, None)

    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / f"{profile.value}.env"
    path.write_text(
        "\n".join(f"{name}={value}" for name, value in values.items()) + "\n",
        encoding="utf-8",
    )
    return path


def test_load_profile_config_returns_path_values_and_typed_settings(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    path = _write_strict_profile(config_dir, Profile.LOCAL)

    loaded = config.load_profile_config(
        Profile.LOCAL,
        config_dir=config_dir,
        environ={"YTS_PROFILE": "local"},
    )

    assert loaded.path == path
    assert loaded.settings.profile == Profile.LOCAL
    assert loaded.values["YTS_DATABASE_URL"].startswith("sqlite+")
    assert loaded.settings.database_url == loaded.values["YTS_DATABASE_URL"]


def test_load_profile_config_uses_python_dotenv_for_multiline_values(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.LOCAL,
        overrides={
            "YTS_OPENAI_BASE_URL": '"https://example.test/v1\npreview"',
        },
    )

    loaded = config.load_profile_config(
        Profile.LOCAL,
        config_dir=config_dir,
        environ={"YTS_PROFILE": "local"},
    )

    assert loaded.values["YTS_OPENAI_BASE_URL"] == "https://example.test/v1\npreview"


def test_load_profile_config_rejects_dotenv_interpolation(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    placeholder = "${YTS_OPENAI_BASE_URL}"
    path = _write_strict_profile(
        config_dir,
        Profile.LOCAL,
        overrides={"YTS_GATEWAY_BASE_URL": placeholder},
    )

    with pytest.raises(ValueError) as exc_info:
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )

    message = str(exc_info.value)
    assert "interpolation is unsupported" in message
    assert f"{path}:6" in message
    assert "YTS_GATEWAY_BASE_URL" in message
    assert placeholder not in message


def test_load_profile_config_allows_literal_dollar_signs(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    gateway_url = "http://127.0.0.1:8799/$catalog"
    _write_strict_profile(
        config_dir,
        Profile.LOCAL,
        overrides={"YTS_GATEWAY_BASE_URL": gateway_url},
    )

    loaded = config.load_profile_config(
        Profile.LOCAL,
        config_dir=config_dir,
        environ={"YTS_PROFILE": "local"},
    )

    assert loaded.values["YTS_GATEWAY_BASE_URL"] == gateway_url


def test_load_profile_config_requires_selected_profile_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()

    with pytest.raises(FileNotFoundError, match=r"local\.env"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_duplicate_assignment_names(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    path = _write_strict_profile(config_dir, Profile.LOCAL)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("YTS_DATABASE_URL=sqlite+aiosqlite:///./duplicate.db\n")

    with pytest.raises(ValueError, match=r"duplicate.*YTS_DATABASE_URL"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_invalid_assignment_lines(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    path = _write_strict_profile(config_dir, Profile.LOCAL)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("this is not an assignment\n")

    with pytest.raises(ValueError, match="invalid env assignment"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_unknown_file_name(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    path = _write_strict_profile(config_dir, Profile.LOCAL)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("YTS_UNKNOWN_SETTING=value\n")

    with pytest.raises(ValueError, match=r"unknown.*YTS_UNKNOWN_SETTING"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_unknown_process_yts_name(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(config_dir, Profile.LOCAL)

    with pytest.raises(ValueError, match=r"unknown.*YTS_UNKNOWN_PROCESS_SETTING"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={
                "YTS_PROFILE": "local",
                "YTS_UNKNOWN_PROCESS_SETTING": "value",
            },
        )


def test_load_profile_config_allows_documented_process_controls(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(config_dir, Profile.LOCAL)

    loaded = config.load_profile_config(
        Profile.LOCAL,
        config_dir=config_dir,
        environ={
            "YTS_PROFILE": "local",
            "YTS_CONFIG_DIR": str(config_dir),
            "YTS_SKIP_STARTUP_DB_BOOTSTRAP": "1",
            "YTS_PORT": "8765",
            "YTS_RUNTIME_DIR": "run/test-runtime",
        },
    )

    assert loaded.settings.profile == Profile.LOCAL
    assert "YTS_RUNTIME_DIR" not in loaded.values


def test_load_profile_config_rejects_file_profile_mismatch(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    path = _write_strict_profile(config_dir, Profile.LOCAL)
    contents = path.read_text(encoding="utf-8")
    path.write_text(contents.replace("YTS_PROFILE=local", "YTS_PROFILE=cloud"), encoding="utf-8")

    with pytest.raises(ValueError, match=r"YTS_PROFILE.*cloud.*selected profile local"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_process_profile_mismatch(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(config_dir, Profile.LOCAL)

    with pytest.raises(ValueError, match=r"process YTS_PROFILE.*cloud.*selected profile local"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "cloud"},
        )


@pytest.mark.parametrize("jwt_secret", ["", "too-short"])
def test_load_profile_config_rejects_empty_or_short_jwt(
    tmp_path: Path,
    jwt_secret: str,
) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.LOCAL,
        overrides={"YTS_AUTH_JWT_SECRET": jwt_secret},
    )

    with pytest.raises(ValueError, match="YTS_AUTH_JWT_SECRET"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_missing_database_url(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.LOCAL,
        omitted={"YTS_DATABASE_URL"},
    )

    with pytest.raises(ValueError, match="YTS_DATABASE_URL must be configured"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_postgres_checkpoint_without_dsn(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.LOCAL,
        overrides={"YTS_LANGGRAPH_CHECKPOINT_BACKEND": "postgres"},
        omitted={"YTS_LANGGRAPH_CHECKPOINT_POSTGRES_DSN"},
    )

    with pytest.raises(
        ValueError,
        match="YTS_LANGGRAPH_CHECKPOINT_POSTGRES_DSN must be configured",
    ):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_local_backend_without_gateway_url(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.LOCAL,
        omitted={"YTS_GATEWAY_BASE_URL"},
    )

    with pytest.raises(ValueError, match="YTS_GATEWAY_BASE_URL must be configured"):
        config.load_profile_config(
            Profile.LOCAL,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "local"},
        )


def test_load_profile_config_rejects_deepseek_model_without_key(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.CLOUD,
        overrides={"YTS_DEEPSEEK_API_KEY": ""},
    )

    with pytest.raises(ValueError, match="YTS_DEEPSEEK_API_KEY must be configured"):
        config.load_profile_config(
            Profile.CLOUD,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "cloud"},
        )


def test_load_profile_config_rejects_openai_fallback_without_key(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.CLOUD,
        overrides={
            "YTS_MODEL_FALLBACKS": '["openai/gpt-4.1-mini"]',
            "YTS_OPENAI_API_KEY": "",
        },
    )

    with pytest.raises(ValueError, match="YTS_OPENAI_API_KEY must be configured"):
        config.load_profile_config(
            Profile.CLOUD,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "cloud"},
        )


def test_load_profile_config_rejects_deepseek_fallback_without_key(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.CLOUD,
        overrides={
            "YTS_DEFAULT_TEXT_MODEL": "openai/gpt-4.1-mini",
            "YTS_MODEL_FALLBACKS": '["deepseek/deepseek-chat"]',
            "YTS_DEEPSEEK_API_KEY": "",
            "YTS_OPENAI_API_KEY": "sk-openai-test",
        },
    )

    with pytest.raises(ValueError, match="YTS_DEEPSEEK_API_KEY must be configured"):
        config.load_profile_config(
            Profile.CLOUD,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "cloud"},
        )


@pytest.mark.parametrize("model", ["openai/gpt-4.1-mini", "gpt-5.5"])
def test_load_profile_config_rejects_openai_compatible_model_without_key(
    tmp_path: Path,
    model: str,
) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(
        config_dir,
        Profile.CLOUD,
        overrides={
            "YTS_DEFAULT_TEXT_MODEL": model,
            "YTS_DEEPSEEK_API_KEY": "",
            "YTS_OPENAI_API_KEY": "",
        },
    )

    with pytest.raises(ValueError, match="YTS_OPENAI_API_KEY must be configured"):
        config.load_profile_config(
            Profile.CLOUD,
            config_dir=config_dir,
            environ={"YTS_PROFILE": "cloud"},
        )


def test_load_profile_config_process_environment_overrides_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "conf"
    _write_strict_profile(config_dir, Profile.LOCAL)

    loaded = config.load_profile_config(
        Profile.LOCAL,
        config_dir=config_dir,
        environ={
            "YTS_PROFILE": "local",
            "YTS_DATABASE_URL": "sqlite+aiosqlite:///./override.db",
        },
    )

    assert loaded.values["YTS_DATABASE_URL"] == "sqlite+aiosqlite:///./override.db"
    assert loaded.settings.database_url == "sqlite+aiosqlite:///./override.db"


def test_settings_rejects_unknown_constructor_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Settings(unknown_setting=True)


def test_core_declares_strict_profile_parser_dependencies() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "core" / "pyproject.toml"
    pyproject = pyproject_path.read_text(encoding="utf-8")

    assert '"python-dotenv>=1.0"' in pyproject
    assert '"tomli>=2.0"' in pyproject


@pytest.mark.parametrize("profile", [Profile.LOCAL, Profile.CLOUD])
def test_example_profile_lists_every_supported_name_once(profile: Profile) -> None:
    example_path = (
        Path(__file__).resolve().parents[1] / "conf" / f"{profile.value}.example.env"
    )
    assignments = [
        line.split("=", 1)
        for line in example_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    names = [name for name, _ in assignments]
    values = dict(assignments)
    expected_names = {"YTS_PROFILE", *config._LEGACY_ENV_MAP}

    assert len(names) == len(set(names))
    assert set(names) == expected_names
    assert values["YTS_PROFILE"] == profile.value
    assert values["YTS_DEEPSEEK_API_KEY"] == ""
    assert values["YTS_OPENAI_API_KEY"] == ""
    assert values["YTS_AUTH_JWT_SECRET"] == ""
    assert values["YTS_LANGGRAPH_CHECKPOINT_POSTGRES_DSN"] == ""
    assert not any("_CMD" in name or "_ARGV" in name for name in names)


def test_settings_exposes_typed_config_sections() -> None:
    settings = Settings(
        profile="cloud",
        database_url="sqlite+aiosqlite:///typed.db",
        database_echo=True,
        inference_backend="cloud",
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
        gateway_base_url="http://127.0.0.1:8799",
        gateway_text_max_tokens=1024,
        gateway_request_timeout_seconds=45,
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
        logging_dir="var/log/yts",
        logging_backend_file="backend-{profile}.log",
        logging_frontend_file="frontend-{profile}.log",
        server_allowed_origins=["http://127.0.0.1:1420", "https://studio.example.test"],
    )

    assert settings.database.url == "sqlite+aiosqlite:///typed.db"
    assert settings.database.echo is True
    assert settings.inference.backend == "cloud"
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
    assert settings.gateway.base_url == "http://127.0.0.1:8799"
    assert settings.gateway.text_max_tokens == 1024
    assert settings.gateway.request_timeout_seconds == 45
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
    assert settings.logging.dir == "var/log/yts"
    assert settings.logging.backend_file == "backend-{profile}.log"
    assert settings.logging.frontend_file == "frontend-{profile}.log"
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
    assert settings.logging_dir == "var/log/yts"
    assert settings.logging_backend_file == "backend-{profile}.log"
    assert settings.logging_frontend_file == "frontend-{profile}.log"
    assert settings.server_allowed_origins == [
        "http://127.0.0.1:1420",
        "https://studio.example.test",
    ]


def test_get_settings_is_cached_until_reloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YTS_INFERENCE_BACKEND", "local")
    reload_settings()

    first = get_settings()
    monkeypatch.setenv("YTS_INFERENCE_BACKEND", "cloud")
    second = get_settings()

    assert second is first
    assert second.inference_backend == "local"

    reloaded = reload_settings()

    assert reloaded is get_settings()
    assert reloaded.inference_backend == "cloud"


def test_settings_reads_profile_config_file_and_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    config_file = config_dir / "cloud.env"
    config_file.write_text(
        "\n".join(
            [
                "YTS_PROFILE=cloud",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_INFERENCE_BACKEND=cloud",
                "YTS_DEFAULT_TEXT_MODEL=deepseek/deepseek-chat",
                "YTS_DEEPSEEK_API_KEY=sk-deepseek-file",
                "YTS_DEEPSEEK_TEXT_MODEL=deepseek/deepseek-chat",
                "YTS_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1",
                "YTS_OPENAI_API_KEY=sk-from-file",
                "YTS_OPENAI_TEXT_MODEL=gpt-4.1",
                "YTS_DATABASE_ECHO=true",
                "YTS_LOGGING_LEVEL=DEBUG",
                "YTS_LOGGING_FORMAT=json",
                "YTS_LOGGING_DIR=var/log/yts",
                "YTS_LOGGING_BACKEND_FILE=backend-{profile}.log",
                "YTS_LOGGING_FRONTEND_FILE=frontend-{profile}.log",
                'YTS_SERVER_ALLOWED_ORIGINS=["http://127.0.0.1:1420","https://studio.example.test"]',
                "YTS_GATEWAY_TEXT_MAX_TOKENS=512",
                "YTS_IMAGE_PROVIDER=openai",
                "YTS_IMAGE_MODEL=gpt-image-1",
                "YTS_AUDIO_EFFECT_PROVIDER=elevenlabs",
                "YTS_AUDIO_EFFECT_MODEL=sound-effects-v1",
                "YTS_MUSIC_PROVIDER=suno",
                "YTS_MUSIC_MODEL=suno-v4.5",
                f"YTS_AUTH_JWT_SECRET={_TEST_JWT_SECRET}",
                "YTS_LANGGRAPH_CHECKPOINT_BACKEND=memory",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("YTS_OPENAI_TEXT_MODEL", "gpt-4.1-mini")

    settings = reload_settings()

    assert settings.inference_backend == "cloud"
    assert settings.default_text_model == "deepseek/deepseek-chat"
    assert settings.deepseek_api_key == "sk-deepseek-file"
    assert settings.deepseek_text_model == "deepseek/deepseek-chat"
    assert settings.deepseek_base_url == "https://api.deepseek.com/v1"
    assert settings.openai_api_key == "sk-from-file"
    assert settings.openai.text_model == "gpt-4.1-mini"
    assert settings.database.echo is True
    assert settings.logging.level == "DEBUG"
    assert settings.logging.format == "json"
    assert settings.logging.dir == "var/log/yts"
    assert settings.logging.backend_file == "backend-{profile}.log"
    assert settings.logging.frontend_file == "frontend-{profile}.log"
    assert settings.server.allowed_origins == [
        "http://127.0.0.1:1420",
        "https://studio.example.test",
    ]
    assert settings.gateway.text_max_tokens == 512
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
    assert settings.inference.backend == "local"
    assert settings.features.allow_custom_skills is True
    assert settings.features.billing_enabled is False
    assert settings.observability.phoenix_enabled is False


def test_cloud_profile_settings_are_explicit_overrides() -> None:
    settings = Settings.for_profile(Profile.CLOUD)

    assert settings.profile == Profile.CLOUD
    assert settings.database.url == "postgresql+asyncpg://localhost/yts"
    assert settings.inference.backend == "cloud"
    assert settings.features.allow_custom_skills is False
    assert settings.features.billing_enabled is True


def test_get_settings_requires_local_profile_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    monkeypatch.setenv("YTS_PROFILE", "local")
    monkeypatch.setenv("YTS_CONFIG_DIR", str(config_dir))

    with pytest.raises(FileNotFoundError, match=r"local\.env"):
        reload_settings()


def test_get_settings_reads_default_local_profile_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_dir = tmp_path / "conf"
    config_dir.mkdir()
    local_file = config_dir / "local.env"
    local_file.write_text(
        "\n".join(
            [
                "YTS_PROFILE=local",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./local.db",
                "YTS_OPENAI_API_KEY=sk-local-file",
                "YTS_OPENAI_TEXT_MODEL=gpt-local-file",
                "YTS_DEFAULT_TEXT_MODEL=openai/gpt-local-file",
                "YTS_INFERENCE_BACKEND=cloud",
                f"YTS_AUTH_JWT_SECRET={_TEST_JWT_SECRET}",
                "YTS_LANGGRAPH_CHECKPOINT_BACKEND=memory",
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
    assert settings.inference_backend == "cloud"


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
