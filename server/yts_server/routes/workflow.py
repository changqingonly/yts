from __future__ import annotations

from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect
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
    stream_resume_workflow_thread,
    stream_workflow_thread,
    workflow_thread_trace,
)

from ..db.session import get_sessionmaker
from ..domains import workflow_history as workflow_history_domain
from ..errors import AppError
from .billing_guard import GenerationBillingGuard, billing_user_if_required
from .dependencies import DbSession

router = APIRouter(prefix="/workflows", tags=["workflows"])
logger = structlog.get_logger(__name__)


class WorkflowThreadRunBody(BaseModel):
    thread_id: str
    user_prompt: str
    node_config: dict[str, dict[str, Any]] = Field(default_factory=dict)


class WorkflowStreamRunMessage(BaseModel):
    type: str
    thread_id: str
    user_prompt: str
    node_config: dict[str, dict[str, Any]] = Field(default_factory=dict)
    authorization: str | None = None


class WorkflowStreamResumeMessage(BaseModel):
    type: str
    node_id: str
    action: str
    patch: dict[str, Any] = Field(default_factory=dict)
    choice: str | None = None
    comment: str = ""
    authorization: str | None = None


class WorkflowHistoryItem(BaseModel):
    workflow_id: str
    thread_id: str
    run_id: str
    title: str
    user_prompt: str
    status: str
    completed_nodes: int
    total_nodes: int
    last_node_id: str
    created_at: str
    updated_at: str


@router.get("/{workflow_id}/template", response_model=WorkflowDefinition)
async def get_workflow_template(workflow_id: str) -> WorkflowDefinition:
    return _require_workflow_template(workflow_id)


@router.websocket("/{workflow_id}/threads/stream")
async def run_workflow_stream(workflow_id: str, websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        message = WorkflowStreamRunMessage.model_validate(await websocket.receive_json())
        if message.type != "run":
            raise ValueError("workflow stream expected type=run")
        _require_workflow_template(workflow_id)
        settings = get_settings()
        checkpointer = build_langgraph_checkpointer(settings)
        async with get_sessionmaker()() as session:
            user = await billing_user_if_required(session, message.authorization)
            async with GenerationBillingGuard(
                session=session,
                user=user,
                request_id=f"{workflow_id}:{message.thread_id}:run-stream:{uuid4().hex}",
                credit_scene="lyrics",
                usage_scene="lyrics",
            ):
                await websocket.send_json({"type": "started", "mode": "run"})
                async for event in stream_workflow_thread(
                    WorkflowRunRequest(
                        workflow_id=workflow_id,
                        thread_id=message.thread_id,
                        user_prompt=message.user_prompt,
                        node_config=message.node_config,
                    ),
                    backend=make_backend(),
                    checkpointer=checkpointer,
                ):
                    if event.type == "result" and event.result is not None:
                        await workflow_history_domain.upsert_workflow_history(
                            session,
                            workflow_id=workflow_id,
                            user_uuid=user.user_uuid if user else None,
                            result=event.result,
                        )
                        await session.commit()
                    await _send_stream_event(websocket, event)
    except WebSocketDisconnect:
        return
    except ValueError as exc:
        logger.warning(
            "workflow.run.stream_failed",
            workflow_id=workflow_id,
            error_type=type(exc).__name__,
            detail=str(exc),
        )
        await websocket.send_json({"type": "error", "detail": str(exc)})
    except AppError as exc:
        logger.warning(
            "workflow.run.stream_failed",
            workflow_id=workflow_id,
            error_type=type(exc).__name__,
            code=exc.code,
            detail=exc.message,
        )
        await websocket.send_json(
            {"type": "error", "code": exc.code, "detail": exc.message}
        )
    finally:
        await _close_websocket(websocket)


@router.websocket("/{workflow_id}/threads/{thread_id}/stream")
async def resume_workflow_stream(workflow_id: str, thread_id: str, websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        message = WorkflowStreamResumeMessage.model_validate(await websocket.receive_json())
        if message.type != "resume":
            raise ValueError("workflow stream expected type=resume")
        _require_workflow_template(workflow_id)
        settings = get_settings()
        checkpointer = build_langgraph_checkpointer(settings)
        decision = HumanDecision(
            node_id=message.node_id,
            action=message.action,
            patch=message.patch,
            choice=message.choice,
            comment=message.comment,
        )
        async with get_sessionmaker()() as session:
            user = await billing_user_if_required(session, message.authorization)
            await websocket.send_json({"type": "started", "mode": "resume"})
            async for event in stream_resume_workflow_thread(
                thread_id=thread_id,
                decision=decision,
                backend=make_backend(),
                checkpointer=checkpointer,
            ):
                if event.type == "result" and event.result is not None:
                    await workflow_history_domain.upsert_workflow_history(
                        session,
                        workflow_id=workflow_id,
                        user_uuid=user.user_uuid if user else None,
                        result=event.result,
                    )
                    await session.commit()
                await _send_stream_event(websocket, event)
    except WebSocketDisconnect:
        return
    except ValueError as exc:
        logger.warning(
            "workflow.resume.stream_failed",
            workflow_id=workflow_id,
            thread_id=thread_id,
            error_type=type(exc).__name__,
            detail=str(exc),
        )
        await websocket.send_json({"type": "error", "detail": str(exc)})
    except AppError as exc:
        logger.warning(
            "workflow.resume.stream_failed",
            workflow_id=workflow_id,
            thread_id=thread_id,
            error_type=type(exc).__name__,
            code=exc.code,
            detail=exc.message,
        )
        await websocket.send_json(
            {"type": "error", "code": exc.code, "detail": exc.message}
        )
    finally:
        await _close_websocket(websocket)


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
        logger.info(
            "workflow.run.requested",
            workflow_id=workflow_id,
            thread_id=req.thread_id,
            prompt_chars=len(req.user_prompt),
            node_config_keys=sorted(req.node_config),
            backend=settings.inference_backend,
        )
        try:
            result = await run_workflow_thread(
                WorkflowRunRequest(
                    workflow_id=workflow_id,
                    thread_id=req.thread_id,
                    user_prompt=req.user_prompt,
                    node_config=req.node_config,
                ),
                backend=make_backend(),
                checkpointer=checkpointer,
            )
            logger.info(
                "workflow.run.completed",
                workflow_id=workflow_id,
                thread_id=req.thread_id,
                run_id=result.run_id,
                status=result.status,
                waiting_node_id=result.waiting.node_id if result.waiting else None,
                trace_node_count=len(result.trace.nodes),
            )
            await workflow_history_domain.upsert_workflow_history(
                session,
                workflow_id=workflow_id,
                user_uuid=user.user_uuid if user else None,
                result=result,
            )
            await session.commit()
            return result
        except ValueError as exc:
            logger.warning(
                "workflow.run.failed",
                workflow_id=workflow_id,
                thread_id=req.thread_id,
                error_type=type(exc).__name__,
                detail=str(exc),
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
    logger.info(
        "workflow.resume.requested",
        workflow_id=workflow_id,
        thread_id=thread_id,
        node_id=decision.node_id,
        action=decision.action,
        patch_keys=sorted(decision.patch),
        has_choice=decision.choice is not None,
    )
    try:
        result = await resume_workflow_thread(
            thread_id=thread_id,
            decision=decision,
            backend=make_backend(),
            checkpointer=checkpointer,
        )
        logger.info(
            "workflow.resume.completed",
            workflow_id=workflow_id,
            thread_id=thread_id,
            run_id=result.run_id,
            status=result.status,
            waiting_node_id=result.waiting.node_id if result.waiting else None,
            trace_node_count=len(result.trace.nodes),
        )
        await workflow_history_domain.upsert_workflow_history(
            session,
            workflow_id=workflow_id,
            user_uuid=user.user_uuid if user else None,
            result=result,
        )
        await session.commit()
        return result
    except ValueError as exc:
        logger.warning(
            "workflow.resume.failed",
            workflow_id=workflow_id,
            thread_id=thread_id,
            node_id=decision.node_id,
            action=decision.action,
            error_type=type(exc).__name__,
            detail=str(exc),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{workflow_id}/threads/history", response_model=list[WorkflowHistoryItem])
async def list_workflow_history(
    workflow_id: str,
    session: DbSession,
    authorization: str | None = Header(default=None),
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    _require_workflow_template(workflow_id)
    user = await billing_user_if_required(session, authorization)
    logger.info(
        "workflow.history.requested",
        workflow_id=workflow_id,
        user_uuid=user.user_uuid if user else None,
        limit=limit,
        offset=offset,
    )
    items = await workflow_history_domain.list_workflow_history(
        session,
        workflow_id=workflow_id,
        user_uuid=user.user_uuid if user else None,
        limit=max(1, min(limit, 100)),
        offset=max(0, offset),
    )
    logger.info(
        "workflow.history.completed",
        workflow_id=workflow_id,
        user_uuid=user.user_uuid if user else None,
        item_count=len(items),
    )
    return items


@router.get("/{workflow_id}/threads/{thread_id}/trace", response_model=WorkflowTrace)
async def get_workflow_trace(workflow_id: str, thread_id: str) -> WorkflowTrace:
    _require_workflow_template(workflow_id)
    settings = get_settings()
    checkpointer = build_langgraph_checkpointer(settings)
    logger.info("workflow.trace.requested", workflow_id=workflow_id, thread_id=thread_id)
    trace = await workflow_thread_trace(thread_id=thread_id, checkpointer=checkpointer)
    logger.info(
        "workflow.trace.completed",
        workflow_id=workflow_id,
        thread_id=thread_id,
        run_id=trace.run_id,
        trace_node_count=len(trace.nodes),
    )
    return trace


def _require_workflow_template(workflow_id: str) -> WorkflowDefinition:
    template = default_workflow_template()
    if workflow_id != template.workflow_id:
        raise HTTPException(status_code=404, detail=f"unsupported workflow_id: {workflow_id}")
    return template


async def _send_stream_event(websocket: WebSocket, event) -> None:
    if event.type == "trace" and event.trace is not None:
        await websocket.send_json({"type": "trace", "trace": event.trace.model_dump(mode="json")})
        return
    if event.type == "result" and event.result is not None:
        await websocket.send_json(
            {"type": "result", "result": event.result.model_dump(mode="json")}
        )
        return
    raise ValueError(f"unsupported workflow stream event: {event.type}")


async def _close_websocket(websocket: WebSocket) -> None:
    try:
        await websocket.close()
    except RuntimeError:
        return
