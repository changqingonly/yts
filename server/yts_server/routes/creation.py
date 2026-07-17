"""创作 / 灵感路由。薄入口:计费包裹(云) + 调 core 编排。"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Cookie, Header
from yts_core.config import get_settings
from yts_core.orchestration import run_creation, run_inspiration
from yts_core.orchestration.checkpointing import build_langgraph_checkpointer
from yts_core.schemas.creation import (
    CreationRequest,
    CreationResult,
    InspirationRequest,
    InspirationResult,
)

from .billing_guard import GenerationBillingGuard, billing_user_if_required
from .dependencies import DbSession

router = APIRouter(prefix="/creation", tags=["creation"])


@router.post("", response_model=CreationResult)
async def create(
    req: CreationRequest,
    session: DbSession,
    authorization: str | None = Header(default=None),
    device_id: str | None = Cookie(default=None, alias="yts-device"),
) -> CreationResult:
    settings = get_settings()
    user = await billing_user_if_required(session, authorization, device_id)
    async with GenerationBillingGuard(
        session=session,
        user=user,
        request_id=f"creation:{req.thread_id or 'sync'}:{uuid4().hex}",
        credit_scene="lyrics",
        usage_scene="lyrics",
    ):
        checkpointer = build_langgraph_checkpointer(settings)
        return await run_creation(req, checkpointer=checkpointer)


@router.post("/inspiration/fill", response_model=InspirationResult)
async def fill_inspiration(
    req: InspirationRequest,
    session: DbSession,
    authorization: str | None = Header(default=None),
    device_id: str | None = Cookie(default=None, alias="yts-device"),
) -> InspirationResult:
    user = await billing_user_if_required(session, authorization, device_id)
    async with GenerationBillingGuard(
        session=session,
        user=user,
        request_id=f"inspiration:{uuid4().hex}",
        credit_scene="inspiration",
        usage_scene=None,
    ):
        return await run_inspiration(req)
