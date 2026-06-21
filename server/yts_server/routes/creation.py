"""创作 / 灵感路由。薄入口:计费包裹(云) + 调 core 编排。"""
from __future__ import annotations

from fastapi import APIRouter

from yts_core.config import get_settings
from yts_core.orchestration import run_creation, run_inspiration
from yts_core.schemas.creation import (
    CreationRequest,
    CreationResult,
    InspirationRequest,
    InspirationResult,
)

from ..billing import tcc

router = APIRouter(prefix="/creation", tags=["creation"])


@router.post("", response_model=CreationResult)
async def create(req: CreationRequest) -> CreationResult:
    settings = get_settings()
    # 云端:三段式计费包裹(本地 profile billing_enabled=False 时直通)
    async with tcc.reservation(scene="creation", enabled=settings.billing_enabled):
        return await run_creation(req)


@router.post("/inspiration/fill", response_model=InspirationResult)
async def fill_inspiration(req: InspirationRequest) -> InspirationResult:
    settings = get_settings()
    async with tcc.reservation(scene="inspiration", enabled=settings.billing_enabled):
        return await run_inspiration(req)
