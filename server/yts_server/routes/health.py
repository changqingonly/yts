from __future__ import annotations

from fastapi import APIRouter
from yts_core import __version__ as core_version
from yts_core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "profile": s.profile.value,
        "core_version": core_version,
        "billing_enabled": s.billing_enabled,
        "allow_custom_skills": s.allow_custom_skills,
    }
