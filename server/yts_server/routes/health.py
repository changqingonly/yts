from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter
from yts_core import __version__ as core_version
from yts_core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    openai_base_url = _url_parts(s.openai_base_url)
    deepseek_base_url = _url_parts(s.deepseek_base_url)
    return {
        "status": "ok",
        "profile": s.profile.value,
        "core_version": core_version,
        "billing_enabled": s.billing_enabled,
        "allow_custom_skills": s.allow_custom_skills,
        "inference_backend": s.inference_backend,
        "default_text_model": s.default_text_model,
        "model_fallbacks": s.model_fallbacks,
        "deepseek_text_model": s.deepseek_text_model,
        "deepseek_base_url_configured": bool(s.deepseek_base_url.strip()),
        "deepseek_base_url_scheme": deepseek_base_url["scheme"],
        "deepseek_base_url_host": deepseek_base_url["host"],
        "deepseek_base_url_port": deepseek_base_url["port"],
        "deepseek_base_url_path": deepseek_base_url["path"],
        "deepseek_request_timeout_seconds": s.deepseek_request_timeout_seconds,
        "deepseek_max_retries": s.deepseek_max_retries,
        "deepseek_api_key_configured": bool(s.deepseek_api_key.strip()),
        "deepseek_api_key_length": len(s.deepseek_api_key),
        "openai_text_model": s.openai_text_model,
        "openai_image_model": s.openai_image_model,
        "openai_speech_model": s.openai_speech_model,
        "openai_base_url_configured": bool(s.openai_base_url.strip()),
        "openai_base_url_scheme": openai_base_url["scheme"],
        "openai_base_url_host": openai_base_url["host"],
        "openai_base_url_port": openai_base_url["port"],
        "openai_base_url_path": openai_base_url["path"],
        "openai_request_timeout_seconds": s.openai_request_timeout_seconds,
        "openai_max_retries": s.openai_max_retries,
        "openai_api_key_configured": bool(s.openai_api_key.strip()),
        "openai_api_key_length": len(s.openai_api_key),
        "gateway_base_url": s.gateway_base_url,
        "gateway_text_max_tokens": s.gateway_text_max_tokens,
        "gateway_request_timeout_seconds": s.gateway_request_timeout_seconds,
        "database_echo": s.database_echo,
        "logging_level": s.logging_level,
        "logging_format": s.logging_format,
        "server_allowed_origins": s.server_allowed_origins,
        "image_provider": s.image_provider,
        "image_model": s.image_model,
        "audio_effect_provider": s.audio_effect_provider,
        "audio_effect_model": s.audio_effect_model,
        "music_provider": s.music_provider,
        "music_model": s.music_model,
    }


def _url_parts(value: str) -> dict[str, str | int | None]:
    if not value.strip():
        return {"scheme": "", "host": "", "port": None, "path": ""}
    parsed = urlparse(value)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "",
        "port": parsed.port,
        "path": parsed.path,
    }
