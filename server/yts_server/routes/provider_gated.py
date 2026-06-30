from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..errors import AppError
from .dependencies import CurrentUser

router = APIRouter(tags=["provider-gated"])


class GenerateRequest(BaseModel):
    prompt: str


@router.post("/images/generate")
async def generate_image(_req: GenerateRequest, _user: CurrentUser) -> dict:
    raise AppError.provider_not_configured("images")


@router.post("/audio-effects/generate")
async def generate_audio_effect(_req: GenerateRequest, _user: CurrentUser) -> dict:
    raise AppError.provider_not_configured("audio_effects")
