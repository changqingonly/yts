from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from yts_core.workflow.runtime import WorkflowRunResult, default_workflow_template

from ..db.models import WorkflowRunHistory


async def upsert_workflow_history(
    session: AsyncSession,
    *,
    workflow_id: str,
    user_uuid: str | None,
    result: WorkflowRunResult,
) -> dict:
    history_id = _history_id(workflow_id, user_uuid, result.thread_id)
    record = await session.get(WorkflowRunHistory, history_id)
    snapshot = _snapshot_from_result(workflow_id, user_uuid, result)
    if record is None:
        record = WorkflowRunHistory(id=history_id, **snapshot)
        session.add(record)
    else:
        for key, value in snapshot.items():
            setattr(record, key, value)
    await session.flush()
    await session.refresh(record)
    return _history_response(record)


async def list_workflow_history(
    session: AsyncSession,
    *,
    workflow_id: str,
    user_uuid: str | None,
    limit: int,
    offset: int,
) -> list[dict]:
    query = select(WorkflowRunHistory).where(WorkflowRunHistory.workflow_id == workflow_id)
    if user_uuid is None:
        query = query.where(WorkflowRunHistory.user_uuid.is_(None))
    else:
        query = query.where(WorkflowRunHistory.user_uuid == user_uuid)
    result = await session.execute(
        query.order_by(WorkflowRunHistory.updated_at.desc()).offset(offset).limit(limit)
    )
    return [_history_response(record) for record in result.scalars().all()]


def _snapshot_from_result(
    workflow_id: str, user_uuid: str | None, result: WorkflowRunResult
) -> dict:
    nodes = result.trace.nodes
    completed_nodes = sum(1 for node in nodes if node.status == "completed")
    last_node = nodes[-1] if nodes else None
    return {
        "workflow_id": workflow_id,
        "user_uuid": user_uuid,
        "thread_id": result.thread_id,
        "run_id": result.run_id,
        "title": _title_from_result(result),
        "user_prompt": _prompt_from_result(result),
        "status": result.status,
        "completed_nodes": completed_nodes,
        "total_nodes": len(default_workflow_template().nodes),
        "last_node_id": last_node.node_id if last_node else "",
    }


def _title_from_result(result: WorkflowRunResult) -> str:
    if result.output is not None and result.output.title.strip():
        return result.output.title.strip()
    if result.waiting is not None:
        title = result.waiting.state_preview.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    for node in reversed(result.trace.nodes):
        for key in ("title", "final_title"):
            value = node.artifact_preview.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "未命名创作"


def _prompt_from_result(result: WorkflowRunResult) -> str:
    for node in result.trace.nodes:
        value = node.artifact_preview.get("user_prompt")
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("workflow history requires validate_request.user_prompt in trace")


def _history_id(workflow_id: str, user_uuid: str | None, thread_id: str) -> str:
    return f"{user_uuid or 'local'}:{workflow_id}:{thread_id}"


def _history_response(record: WorkflowRunHistory) -> dict:
    return {
        "workflow_id": record.workflow_id,
        "thread_id": record.thread_id,
        "run_id": record.run_id,
        "title": record.title,
        "user_prompt": record.user_prompt,
        "status": record.status,
        "completed_nodes": record.completed_nodes,
        "total_nodes": record.total_nodes,
        "last_node_id": record.last_node_id,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }
