"""
运行配置入口。所有 Python 侧配置统一由 Pydantic Settings 装配。

配置来源顺序由 pydantic-settings 处理:初始化参数 > 环境变量 > profile env file > 默认值。
默认按 profile 读取项目 `conf/{profile}.env`;如需替换配置目录,显式设置 `YTS_CONFIG_DIR`。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_LEGACY_ENV_MAP = {
    "YTS_DATABASE_URL": ("database", "url"),
    "YTS_DATABASE_ECHO": ("database", "echo"),
    "YTS_DEFAULT_TEXT_MODEL": ("inference", "default_text_model"),
    "YTS_MODEL_FALLBACKS": ("inference", "model_fallbacks"),
    "YTS_INFERENCE_BACKEND": ("inference", "backend"),
    "YTS_DEEPSEEK_API_KEY": ("deepseek", "api_key"),
    "YTS_DEEPSEEK_TEXT_MODEL": ("deepseek", "text_model"),
    "YTS_DEEPSEEK_BASE_URL": ("deepseek", "base_url"),
    "YTS_DEEPSEEK_REQUEST_TIMEOUT_SECONDS": ("deepseek", "request_timeout_seconds"),
    "YTS_DEEPSEEK_MAX_RETRIES": ("deepseek", "max_retries"),
    "YTS_OPENAI_API_KEY": ("openai", "api_key"),
    "YTS_OPENAI_TEXT_MODEL": ("openai", "text_model"),
    "YTS_OPENAI_IMAGE_MODEL": ("openai", "image_model"),
    "YTS_OPENAI_SPEECH_MODEL": ("openai", "speech_model"),
    "YTS_OPENAI_BASE_URL": ("openai", "base_url"),
    "YTS_OPENAI_REQUEST_TIMEOUT_SECONDS": ("openai", "request_timeout_seconds"),
    "YTS_OPENAI_MAX_RETRIES": ("openai", "max_retries"),
    "YTS_GATEWAY_BASE_URL": ("gateway", "base_url"),
    "YTS_GATEWAY_TEXT_MAX_TOKENS": ("gateway", "text_max_tokens"),
    "YTS_GATEWAY_REQUEST_TIMEOUT_SECONDS": ("gateway", "request_timeout_seconds"),
    "YTS_IMAGE_PROVIDER": ("image", "provider"),
    "YTS_IMAGE_MODEL": ("image", "model"),
    "YTS_AUDIO_EFFECT_PROVIDER": ("audio_effect", "provider"),
    "YTS_AUDIO_EFFECT_MODEL": ("audio_effect", "model"),
    "YTS_MUSIC_PROVIDER": ("music", "provider"),
    "YTS_MUSIC_MODEL": ("music", "model"),
    "YTS_ALLOW_CUSTOM_SKILLS": ("features", "allow_custom_skills"),
    "YTS_BILLING_ENABLED": ("features", "billing_enabled"),
    "YTS_PHOENIX_ENABLED": ("observability", "phoenix_enabled"),
    "YTS_AUTH_JWT_SECRET": ("auth", "jwt_secret"),
    "YTS_AUTH_ACCESS_TOKEN_TTL_SECONDS": ("auth", "access_token_ttl_seconds"),
    "YTS_AVATAR_STORAGE_DIR": ("storage", "avatar_dir"),
    "YTS_LOCAL_IMPORT_STORAGE_DIR": ("storage", "local_import_dir"),
    "YTS_LANGGRAPH_CHECKPOINT_BACKEND": ("langgraph", "checkpoint_backend"),
    "YTS_LANGGRAPH_CHECKPOINT_POSTGRES_DSN": ("langgraph", "checkpoint_postgres_dsn"),
    "YTS_LOGGING_LEVEL": ("logging", "level"),
    "YTS_LOGGING_FORMAT": ("logging", "format"),
    "YTS_LOGGING_DIR": ("logging", "dir"),
    "YTS_LOGGING_BACKEND_FILE": ("logging", "backend_file"),
    "YTS_LOGGING_FRONTEND_FILE": ("logging", "frontend_file"),
    "YTS_SERVER_ALLOWED_ORIGINS": ("server", "allowed_origins"),
}

_JSON_LIST_ENV_NAMES = {"YTS_MODEL_FALLBACKS", "YTS_SERVER_ALLOWED_ORIGINS"}


class Profile(str, Enum):
    CLOUD = "cloud"
    LOCAL = "local"


class DatabaseSettings(BaseModel):
    url: str = "postgresql+asyncpg://localhost/yts"
    echo: bool = False


class InferenceSettings(BaseModel):
    backend: str = "cloud"
    default_text_model: str = "deepseek/deepseek-chat"
    model_fallbacks: list[str] = Field(default_factory=lambda: ["openai/qwen-max"])


class OpenAISettings(BaseModel):
    api_key: SecretStr = SecretStr("")
    text_model: str = "gpt-5.5"
    image_model: str = "gpt-image-1"
    speech_model: str = "gpt-4o-mini-tts"
    base_url: str = ""
    request_timeout_seconds: float = 180.0
    max_retries: int = Field(default=0, ge=0)

    @property
    def api_key_value(self) -> str:
        return self.api_key.get_secret_value()


class DeepSeekSettings(BaseModel):
    api_key: SecretStr = SecretStr("")
    text_model: str = "deepseek/deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    request_timeout_seconds: float = 180.0
    max_retries: int = Field(default=0, ge=0)

    @property
    def api_key_value(self) -> str:
        return self.api_key.get_secret_value()


class GatewaySettings(BaseModel):
    base_url: str = "http://127.0.0.1:8799"
    text_max_tokens: int = Field(default=256, gt=0)
    request_timeout_seconds: float = Field(default=120.0, gt=0)


class GenerationProviderSettings(BaseModel):
    provider: str = ""
    model: str = ""


class FeatureSettings(BaseModel):
    allow_custom_skills: bool = False
    billing_enabled: bool = True


class ObservabilitySettings(BaseModel):
    phoenix_enabled: bool = False


_DEVELOPMENT_JWT_SECRET = "dev-yts-auth-secret-that-is-long-enough-for-hs256"


class AuthSettings(BaseModel):
    production: bool = False
    jwt_secret: SecretStr = SecretStr(_DEVELOPMENT_JWT_SECRET)
    jwt_active_kid: str = "primary"
    issuer: str = "yts"
    audience: str = "yts-client"
    access_token_ttl_seconds: int = Field(default=30 * 60, gt=0)
    refresh_sliding_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0)
    refresh_absolute_ttl_seconds: int = Field(default=90 * 24 * 60 * 60, gt=0)
    cookie_secure: bool = False
    cookie_domain: str = ""
    worker_count: int = Field(default=1, gt=0)
    rate_limit_backend: str = "memory"
    trusted_proxies: list[str] = Field(default_factory=list)

    @property
    def jwt_secret_value(self) -> str:
        return self.jwt_secret.get_secret_value()


class StorageSettings(BaseModel):
    avatar_dir: str = "run/avatars"
    local_import_dir: str = "run/local_imports"


class LangGraphSettings(BaseModel):
    checkpoint_backend: str = "postgres"
    checkpoint_postgres_dsn: str = (
        "postgresql://hongcq:hongcq@127.0.0.1/lss?connect_timeout=5&gssencmode=disable"
    )


class LoggingSettings(BaseModel):
    level: str = "INFO"
    format: str = "auto"
    dir: str = Field(default="run", min_length=1)
    backend_file: str = Field(default="yts-server-{profile}.log", min_length=1)
    frontend_file: str = Field(default="yts-frontend-{profile}.log", min_length=1)


class ServerSettings(BaseModel):
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            # 打包态 Tauri webview 通过自定义协议加载前端资源,请求 Origin 固定为此值(macOS/Linux)。
            # 与上面两个 devUrl(`tauri dev`)来源并列,而非替代——packaged 二进制不读取 conf/*.env
            # (PyInstaller onefile 的 __file__ 不落在项目 conf/ 旁),必须靠此处代码默认值放行。
            "tauri://localhost",
        ]
    )


class DesktopSettings(BaseModel):
    enabled: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="YTS_",
        env_file=None,
        env_nested_delimiter="__",
        extra="ignore",
        validate_default=True,
    )

    profile: Profile = Profile.CLOUD
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    deepseek: DeepSeekSettings = Field(default_factory=DeepSeekSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    image: GenerationProviderSettings = Field(
        default_factory=lambda: GenerationProviderSettings(provider="openai", model="gpt-image-1")
    )
    audio_effect: GenerationProviderSettings = Field(default_factory=GenerationProviderSettings)
    music: GenerationProviderSettings = Field(default_factory=GenerationProviderSettings)
    features: FeatureSettings = Field(default_factory=FeatureSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    langgraph: LangGraphSettings = Field(default_factory=LangGraphSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    desktop: DesktopSettings = Field(default_factory=DesktopSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            _legacy_env_settings_source,
            dotenv_settings,
            _legacy_dotenv_settings_source(dotenv_settings),
            _ProfileDefaultsSettingsSource(settings_cls),
            file_secret_settings,
        )

    def __init__(self, **values: Any) -> None:
        super().__init__(**_coerce_legacy_settings(values))

    @classmethod
    def for_profile(cls, profile: Profile | str, **values: Any) -> Settings:
        profile_value = Profile(profile)
        defaults = _profile_defaults(profile_value)
        defaults.update(_coerce_legacy_settings(values))
        return cls(**defaults)

    def for_local(self) -> Settings:
        """返回本地档覆盖(桌面 sidecar 用)。"""
        return _apply_profile_defaults(self, Profile.LOCAL)

    @model_validator(mode="after")
    def validate_security_settings(self) -> Settings:
        if len(self.auth.jwt_secret_value.encode("utf-8")) < 32:
            raise ValueError("auth_jwt_secret must be at least 32 bytes for HS256")
        if self.auth.rate_limit_backend == "memory" and self.auth.worker_count != 1:
            raise ValueError("in-memory rate limiting requires one worker")
        if self.auth.production:
            if self.auth.jwt_secret_value == _DEVELOPMENT_JWT_SECRET:
                raise ValueError("production auth requires an explicit signing key")
            if not self.auth.cookie_secure:
                raise ValueError("production auth requires secure cookies")
            if self.profile != Profile.CLOUD:
                raise ValueError("production auth requires the cloud profile")
        return self

    @property
    def database_url(self) -> str:
        return self.database.url

    @property
    def database_echo(self) -> bool:
        return self.database.echo

    @property
    def default_text_model(self) -> str:
        return self.inference.default_text_model

    @property
    def model_fallbacks(self) -> list[str]:
        return self.inference.model_fallbacks

    @property
    def inference_backend(self) -> str:
        return self.inference.backend

    @property
    def deepseek_api_key(self) -> str:
        return self.deepseek.api_key_value

    @property
    def deepseek_text_model(self) -> str:
        return self.deepseek.text_model

    @property
    def deepseek_base_url(self) -> str:
        return self.deepseek.base_url

    @property
    def deepseek_request_timeout_seconds(self) -> float:
        return self.deepseek.request_timeout_seconds

    @property
    def deepseek_max_retries(self) -> int:
        return self.deepseek.max_retries

    @property
    def openai_api_key(self) -> str:
        return self.openai.api_key_value

    @property
    def openai_text_model(self) -> str:
        return self.openai.text_model

    @property
    def openai_image_model(self) -> str:
        return self.openai.image_model

    @property
    def openai_speech_model(self) -> str:
        return self.openai.speech_model

    @property
    def openai_base_url(self) -> str:
        return self.openai.base_url

    @property
    def openai_request_timeout_seconds(self) -> float:
        return self.openai.request_timeout_seconds

    @property
    def openai_max_retries(self) -> int:
        return self.openai.max_retries

    @property
    def gateway_base_url(self) -> str:
        return self.gateway.base_url

    @property
    def gateway_text_max_tokens(self) -> int:
        return self.gateway.text_max_tokens

    @property
    def gateway_request_timeout_seconds(self) -> float:
        return self.gateway.request_timeout_seconds

    @property
    def image_provider(self) -> str:
        return self.image.provider

    @property
    def image_model(self) -> str:
        return self.image.model

    @property
    def audio_effect_provider(self) -> str:
        return self.audio_effect.provider

    @property
    def audio_effect_model(self) -> str:
        return self.audio_effect.model

    @property
    def music_provider(self) -> str:
        return self.music.provider

    @property
    def music_model(self) -> str:
        return self.music.model

    @property
    def allow_custom_skills(self) -> bool:
        return self.features.allow_custom_skills

    @property
    def billing_enabled(self) -> bool:
        return self.features.billing_enabled

    @property
    def phoenix_enabled(self) -> bool:
        return self.observability.phoenix_enabled

    @property
    def auth_jwt_secret(self) -> str:
        return self.auth.jwt_secret_value

    @property
    def auth_access_token_ttl_seconds(self) -> int:
        return self.auth.access_token_ttl_seconds

    @property
    def avatar_storage_dir(self) -> str:
        return self.storage.avatar_dir

    @property
    def local_import_storage_dir(self) -> str:
        return self.storage.local_import_dir

    @property
    def langgraph_checkpoint_backend(self) -> str:
        return self.langgraph.checkpoint_backend

    @property
    def langgraph_checkpoint_postgres_dsn(self) -> str:
        return self.langgraph.checkpoint_postgres_dsn

    @property
    def logging_level(self) -> str:
        return self.logging.level

    @property
    def logging_format(self) -> str:
        return self.logging.format

    @property
    def logging_dir(self) -> str:
        return self.logging.dir

    @property
    def logging_backend_file(self) -> str:
        return self.logging.backend_file

    @property
    def logging_frontend_file(self) -> str:
        return self.logging.frontend_file

    @property
    def server_allowed_origins(self) -> list[str]:
        return self.server.allowed_origins


def settings_from_env_mapping(mapping: Mapping[str, Any]) -> Settings:
    profile_value = _mapping_value(mapping, "YTS_PROFILE")
    profile = Profile(profile_value) if profile_value else Profile.CLOUD
    values = _deep_merge(_profile_defaults(profile), _legacy_settings_from_mapping(mapping))
    values["profile"] = profile
    return Settings.model_validate(values)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _reject_removed_config_knobs()
    profile = _configured_profile()
    env_file = _profile_config_file(profile)
    return Settings(_env_file=env_file)


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


def _reject_removed_config_knobs() -> None:
    import os

    removed_names = ("YTS_CONFIG_FILE", "YTS_CONFIG_HOME")
    configured = [name for name in removed_names if os.environ.get(name, "").strip()]
    if configured:
        names = ", ".join(configured)
        raise ValueError(
            f"{names} is no longer supported; use project conf/{{profile}}.env "
            "or set YTS_CONFIG_DIR to a directory containing local.env/cloud.env"
        )


def _profile_config_file(profile: Profile) -> Path | None:
    path = _profile_config_path(profile)
    if path.is_file():
        return path
    return None


def _profile_config_path(profile: Profile) -> Path:
    return _config_dir() / f"{profile.value}.env"


def _config_dir() -> Path:
    import os

    configured = os.environ.get("YTS_CONFIG_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"YTS_CONFIG_DIR does not exist or is not a directory: {path}")
        return path
    return Path(__file__).resolve().parents[2] / "conf"


def _configured_profile() -> Profile:
    import os

    env_profile = os.environ.get("YTS_PROFILE", "").strip()
    if env_profile:
        return Profile(env_profile)
    return Profile.CLOUD


def _profile_defaults(profile: Profile) -> dict[str, Any]:
    if profile == Profile.CLOUD:
        return {
            "profile": Profile.CLOUD,
            "database": {"url": "postgresql+asyncpg://localhost/yts"},
            "inference": {"backend": "cloud"},
            "features": {"allow_custom_skills": False, "billing_enabled": True},
            "observability": {"phoenix_enabled": False},
        }
    if profile == Profile.LOCAL:
        return {
            "profile": Profile.LOCAL,
            "database": {"url": "sqlite+aiosqlite:///./yts_local.db"},
            "inference": {"backend": "local"},
            "features": {"allow_custom_skills": True, "billing_enabled": False},
            "observability": {"phoenix_enabled": False},
        }
    raise ValueError(f"unsupported profile: {profile}")


class _ProfileDefaultsSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        profile_value = self.current_state.get("profile", Profile.CLOUD)
        return _profile_defaults(Profile(profile_value))


def _apply_profile_defaults(settings: Settings, profile: Profile) -> Settings:
    defaults = Settings.for_profile(profile)
    return defaults.model_copy(
        update={
            "deepseek": settings.deepseek,
            "openai": settings.openai,
            "gateway": settings.gateway,
            "image": settings.image,
            "audio_effect": settings.audio_effect,
            "music": settings.music,
            "auth": settings.auth,
            "storage": settings.storage,
            "langgraph": settings.langgraph,
            "logging": settings.logging,
            "server": settings.server,
            "desktop": settings.desktop,
        }
    )


def _coerce_legacy_settings(values: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(values)
    _move(coerced, "database_url", "database", "url")
    _move(coerced, "database_echo", "database", "echo")
    _move(coerced, "default_text_model", "inference", "default_text_model")
    _move(coerced, "model_fallbacks", "inference", "model_fallbacks")
    _move(coerced, "inference_backend", "inference", "backend")
    _move(coerced, "deepseek_api_key", "deepseek", "api_key")
    _move(coerced, "deepseek_text_model", "deepseek", "text_model")
    _move(coerced, "deepseek_base_url", "deepseek", "base_url")
    _move(
        coerced,
        "deepseek_request_timeout_seconds",
        "deepseek",
        "request_timeout_seconds",
    )
    _move(coerced, "deepseek_max_retries", "deepseek", "max_retries")
    _move(coerced, "openai_api_key", "openai", "api_key")
    _move(coerced, "openai_text_model", "openai", "text_model")
    _move(coerced, "openai_image_model", "openai", "image_model")
    _move(coerced, "openai_speech_model", "openai", "speech_model")
    _move(coerced, "openai_base_url", "openai", "base_url")
    _move(coerced, "openai_request_timeout_seconds", "openai", "request_timeout_seconds")
    _move(coerced, "openai_max_retries", "openai", "max_retries")
    _move(coerced, "gateway_base_url", "gateway", "base_url")
    _move(coerced, "gateway_text_max_tokens", "gateway", "text_max_tokens")
    _move(coerced, "gateway_request_timeout_seconds", "gateway", "request_timeout_seconds")
    _move(coerced, "image_provider", "image", "provider")
    _move(coerced, "image_model", "image", "model")
    _move(coerced, "audio_effect_provider", "audio_effect", "provider")
    _move(coerced, "audio_effect_model", "audio_effect", "model")
    _move(coerced, "music_provider", "music", "provider")
    _move(coerced, "music_model", "music", "model")
    _move(coerced, "allow_custom_skills", "features", "allow_custom_skills")
    _move(coerced, "billing_enabled", "features", "billing_enabled")
    _move(coerced, "phoenix_enabled", "observability", "phoenix_enabled")
    _move(coerced, "auth_jwt_secret", "auth", "jwt_secret")
    _move(coerced, "auth_access_token_ttl_seconds", "auth", "access_token_ttl_seconds")
    _move(coerced, "avatar_storage_dir", "storage", "avatar_dir")
    _move(coerced, "local_import_storage_dir", "storage", "local_import_dir")
    _move(coerced, "langgraph_checkpoint_backend", "langgraph", "checkpoint_backend")
    _move(
        coerced,
        "langgraph_checkpoint_postgres_dsn",
        "langgraph",
        "checkpoint_postgres_dsn",
    )
    _move(coerced, "server_allowed_origins", "server", "allowed_origins")
    _move(coerced, "logging_level", "logging", "level")
    _move(coerced, "logging_format", "logging", "format")
    _move(coerced, "logging_dir", "logging", "dir")
    _move(coerced, "logging_backend_file", "logging", "backend_file")
    _move(coerced, "logging_frontend_file", "logging", "frontend_file")
    return coerced


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _legacy_env_settings_source() -> dict[str, Any]:
    import os

    return _legacy_settings_from_mapping(os.environ)


def _legacy_dotenv_settings_source(dotenv_settings) -> Any:
    def load() -> dict[str, Any]:
        return _legacy_settings_from_mapping(getattr(dotenv_settings, "env_vars", {}))

    return load


def _legacy_settings_from_mapping(mapping: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for env_name, (section, target) in _LEGACY_ENV_MAP.items():
        value = _mapping_value(mapping, env_name)
        if value is None:
            continue
        value = _decode_legacy_env_value(env_name, value)
        section_values = data.setdefault(section, {})
        section_values[target] = value
    return data


def _decode_legacy_env_value(env_name: str, value: Any) -> Any:
    if env_name not in _JSON_LIST_ENV_NAMES or not isinstance(value, str):
        return value
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        raise ValueError(f"{env_name} must be a JSON array of strings")
    return decoded


def _mapping_value(mapping: Any, env_name: str) -> Any:
    for key in (env_name, env_name.lower()):
        value = mapping.get(key) if hasattr(mapping, "get") else None
        if value is not None:
            return value
    return None


def _move(values: dict[str, Any], source: str, section: str, target: str) -> None:
    if source not in values:
        return
    section_values = values.get(section)
    if section_values is None:
        section_values = {}
        values[section] = section_values
    if not isinstance(section_values, dict):
        raise TypeError(f"{section} must be a mapping when {source} is provided")
    if target in section_values:
        raise ValueError(f"settings cannot define both {source} and {section}.{target}")
    section_values[target] = values.pop(source)
