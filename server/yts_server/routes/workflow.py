from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from yts_core.config import get_settings
from yts_core.inference import make_backend
from yts_core.orchestration.checkpointing import build_langgraph_checkpointer
from yts_core.workflow.runtime import (
    HumanDecision,
    WorkflowDefinition,
    WorkflowRunRequest,
    WorkflowRunResult,
    WorkflowTrace,
    default_workflow_template,
    resume_workflow_thread,
    run_workflow_thread,
    workflow_thread_trace,
)

from .billing_guard import GenerationBillingGuard, billing_user_if_required
from .dependencies import DbSession

router = APIRouter(prefix="/workflows", tags=["workflows"])
logger = logging.getLogger(__name__)


class WorkflowThreadRunBody(BaseModel):
    thread_id: str
    user_prompt: str
    node_config: dict[str, dict[str, Any]] = Field(default_factory=dict)


@router.get("/{workflow_id}/template", response_model=WorkflowDefinition)
async def get_workflow_template(workflow_id: str) -> WorkflowDefinition:
    return _require_workflow_template(workflow_id)


@router.post("/{workflow_id}/threads", response_model=WorkflowRunResult)
async def run_workflow(
    workflow_id: str,
    req: WorkflowThreadRunBody,
    session: DbSession,
    authorization: str | None = Header(default=None),
) -> WorkflowRunResult:
    settings = get_settings()
    checkpointer = build_langgraph_checkpointer(settings)
    user = await billing_user_if_required(session, authorization)
    async with GenerationBillingGuard(
        session=session,
        user=user,
        request_id=f"{workflow_id}:{req.thread_id}:run:{uuid4().hex}",
        credit_scene="lyrics",
        usage_scene="lyrics",
    ):
        try:
            return await run_workflow_thread(
                WorkflowRunRequest(
                    workflow_id=workflow_id,
                    thread_id=req.thread_id,
                    user_prompt=req.user_prompt,
                    node_config=req.node_config,
                ),
                backend=make_backend(),
                checkpointer=checkpointer,
            )
        except ValueError as exc:
            logger.warning(
                "Workflow run failed workflow_id=%s thread_id=%s detail=%s",
                workflow_id,
                req.thread_id,
                str(exc),
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{workflow_id}/threads/{thread_id}/resume", response_model=WorkflowRunResult)
async def resume_workflow(
    workflow_id: str,
    thread_id: str,
    decision: HumanDecision,
    session: DbSession,
    authorization: str | None = Header(default=None),
) -> WorkflowRunResult:
    _require_workflow_template(workflow_id)
    settings = get_settings()
    checkpointer = build_langgraph_checkpointer(settings)
    user = await billing_user_if_required(session, authorization)
    async with GenerationBillingGuard(
        session=session,
        user=user,
        request_id=f"{workflow_id}:{thread_id}:resume:{decision.node_id}:{decision.action}:{uuid4().hex}",
        credit_scene="lyrics",
        usage_scene="lyrics",
    ):
        try:
            return await resume_workflow_thread(
                thread_id=thread_id,
                decision=decision,
                backend=make_backend(),
                checkpointer=checkpointer,
            )
        except ValueError as exc:
            logger.warning(
                "Workflow resume failed workflow_id=%s thread_id=%s node_id=%s action=%s detail=%s",
                workflow_id,
                thread_id,
                decision.node_id,
                decision.action,
                str(exc),
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{workflow_id}/threads/{thread_id}/trace", response_model=WorkflowTrace)
async def get_workflow_trace(workflow_id: str, thread_id: str) -> WorkflowTrace:
    _require_workflow_template(workflow_id)
    settings = get_settings()
    checkpointer = build_langgraph_checkpointer(settings)
    return await workflow_thread_trace(thread_id=thread_id, checkpointer=checkpointer)


def _require_workflow_template(workflow_id: str) -> WorkflowDefinition:
    template = default_workflow_template()
    if workflow_id != template.workflow_id:
        raise HTTPException(status_code=404, detail=f"unsupported workflow_id: {workflow_id}")
    return template
