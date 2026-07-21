from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import Future
from threading import Lock, Thread
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

import structlog
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from yts_core.orchestration.flow_builder import workflow_config
from yts_core.orchestration.flows.pro_lyrics import PRO_STAGE_ORDER
from yts_core.orchestration.nodes.pro_lyrics import ProLyricsNodes
from yts_core.orchestration.prompt_packs import resolve_prompt_pack
from yts_core.orchestration.state import CreationState
from yts_core.schemas.creation import CreationResult

logger = structlog.get_logger(__name__)


class WorkflowCapabilities(BaseModel):
    locked_edges: bool = True
    editable_node_config: bool = True
    future_editable_graph: bool = True


class WorkflowNodeDefinition(BaseModel):
    id: str
    type: str
    label: str
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdgeDefinition(BaseModel):
    source: str
    target: str
    condition: str | None = None


class WorkflowDefinition(BaseModel):
    workflow_id: str
    version: int = 1
    start_node_id: str
    nodes: list[WorkflowNodeDefinition]
    edges: list[WorkflowEdgeDefinition]
    capabilities: WorkflowCapabilities = Field(default_factory=WorkflowCapabilities)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(BaseModel):
    workflow_id: str
    thread_id: str
    user_prompt: str
    node_config: dict[str, dict[str, Any]] = Field(default_factory=dict)


class HumanDecision(BaseModel):
    node_id: str
    action: Literal["approve", "reject", "edit", "choose", "accept", "rerun"]
    patch: dict[str, Any] = Field(default_factory=dict)
    choice: str | None = None
    comment: str = ""


class WaitingForHuman(BaseModel):
    node_id: str
    kind: str
    prompt: str
    actions: list[str]
    editable_fields: list[str] = Field(default_factory=list)
    state_preview: dict[str, Any] = Field(default_factory=dict)


class WorkflowTraceNode(BaseModel):
    node_id: str
    span_id: str
    duration_ms: int
    node_type: str
    status: Literal["completed", "waiting", "pending"]
    stage_count: int = 0
    note: str | None = None
    summary: str = ""
    artifact_preview: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    llm_call: dict[str, Any] | None = None


class WorkflowTrace(BaseModel):
    workflow_id: str
    workflow_version: int
    thread_id: str
    run_id: str
    nodes: list[WorkflowTraceNode] = Field(default_factory=list)
    phoenix_trace_id: str | None = None


class WorkflowRunResult(BaseModel):
    workflow_id: str
    thread_id: str
    run_id: str
    status: Literal["waiting", "completed"]
    waiting: WaitingForHuman | None = None
    output: CreationResult | None = None
    trace: WorkflowTrace


class WorkflowStreamEvent(BaseModel):
    type: Literal["trace", "result", "node_status"]
    trace: WorkflowTrace | None = None
    result: WorkflowRunResult | None = None
    node_id: str | None = None
    status: str | None = None
    attempt: int | None = None
    detail: str | None = None


class WorkflowState(CreationState, total=False):
    workflow_id: str
    workflow_version: int
    node_config: dict[str, dict[str, Any]]
    trace_nodes: list[dict[str, Any]]
    creation_result: dict[str, Any]
    node_repairs: dict[str, list[dict[str, Any]]]


_PRO_STAGE_LOOP_LOCK = Lock()
_PRO_STAGE_LOOP: asyncio.AbstractEventLoop | None = None
_PRO_STAGE_LOOP_THREAD: Thread | None = None


PRO_STAGE_LABELS = {
    "validate_request": "校验请求",
    "parse_intent": "解析意图",
    "build_song_brief": "歌曲简报",
    "plan_music_style": "音乐风格",
    "hook_lab": "Hook 实验",
    "draft_structure_blueprints": "结构蓝图",
    "critique_structure": "结构评审",
    "plan_style_prompt": "风格提示",
    "generate_lyrics": "歌词生成",
    "review_quality": "质量评审",
    "repair_lyrics": "歌词修复",
    "normalize_suno_format": "Suno 归一",
    "refine_title": "标题精修",
    "build_response": "组装响应",
}


def default_workflow_template() -> WorkflowDefinition:
    pro_nodes = [
        WorkflowNodeDefinition(
            id=stage,
            type="pro_stage",
            label=_pro_stage_label(stage),
            config={"stage": stage},
        )
        for stage in PRO_STAGE_ORDER
    ]
    nodes = [*pro_nodes]
    nodes.append(
        WorkflowNodeDefinition(
            id="final_review",
            type="hitl_review",
            label="最终评审",
            config={
                "actions": ["accept", "edit", "rerun"],
                "editable_fields": ["title", "style", "lyrics"],
            },
        )
    )
    nodes.append(WorkflowNodeDefinition(id="done", type="output", label="完成"))
    return WorkflowDefinition(
        workflow_id="pro_creation_hitl_v1",
        version=1,
        start_node_id="validate_request",
        nodes=nodes,
        edges=[
            WorkflowEdgeDefinition(source="validate_request", target="parse_intent"),
            WorkflowEdgeDefinition(source="parse_intent", target="build_song_brief"),
            WorkflowEdgeDefinition(source="build_song_brief", target="plan_music_style"),
            WorkflowEdgeDefinition(source="plan_music_style", target="hook_lab"),
            WorkflowEdgeDefinition(source="hook_lab", target="draft_structure_blueprints"),
            WorkflowEdgeDefinition(
                source="draft_structure_blueprints", target="critique_structure"
            ),
            WorkflowEdgeDefinition(source="critique_structure", target="plan_style_prompt"),
            WorkflowEdgeDefinition(source="plan_style_prompt", target="generate_lyrics"),
            WorkflowEdgeDefinition(source="generate_lyrics", target="review_quality"),
            WorkflowEdgeDefinition(source="review_quality", target="repair_lyrics"),
            WorkflowEdgeDefinition(source="repair_lyrics", target="normalize_suno_format"),
            WorkflowEdgeDefinition(source="normalize_suno_format", target="refine_title"),
            WorkflowEdgeDefinition(source="refine_title", target="build_response"),
            WorkflowEdgeDefinition(source="build_response", target="final_review"),
            WorkflowEdgeDefinition(source="final_review", target="done"),
        ],
        metadata={"template_name": "Pro 创作 HITL"},
    )


async def run_workflow_thread(
    request: WorkflowRunRequest,
    *,
    backend,
    checkpointer,
) -> WorkflowRunResult:
    started_at = perf_counter()
    state = _initial_workflow_state(request, checkpointer=checkpointer)
    logger.info(
        "workflow.thread.started",
        workflow_id=request.workflow_id,
        thread_id=request.thread_id.strip(),
        run_id=state["run_id"],
        prompt_chars=len(request.user_prompt),
        node_config_keys=sorted(request.node_config),
        backend=getattr(backend, "name", type(backend).__name__),
    )
    graph = _build_template_graph(
        default_workflow_template(), backend=backend, checkpointer=checkpointer
    )
    config = workflow_config(
        checkpointer=checkpointer, thread_id=request.thread_id.strip(), run_id=state["run_id"]
    )
    try:
        result = await asyncio.to_thread(graph.invoke, state, config)
        run_result = _run_result_from_state(result)
        logger.info(
            "workflow.thread.completed",
            workflow_id=request.workflow_id,
            thread_id=request.thread_id.strip(),
            run_id=run_result.run_id,
            status=run_result.status,
            waiting_node_id=run_result.waiting.node_id if run_result.waiting else None,
            trace_node_count=len(run_result.trace.nodes),
            duration_ms=_elapsed_ms(started_at),
        )
        return run_result
    except Exception as exc:
        logger.exception(
            "workflow.thread.failed",
            workflow_id=request.workflow_id,
            thread_id=request.thread_id.strip(),
            run_id=state["run_id"],
            error_type=type(exc).__name__,
            duration_ms=_elapsed_ms(started_at),
        )
        raise


async def stream_workflow_thread(
    request: WorkflowRunRequest,
    *,
    backend,
    checkpointer,
) -> AsyncIterator[WorkflowStreamEvent]:
    started_at = perf_counter()
    state = _initial_workflow_state(request, checkpointer=checkpointer)
    logger.info(
        "workflow.thread.stream_started",
        workflow_id=request.workflow_id,
        thread_id=request.thread_id.strip(),
        run_id=state["run_id"],
        prompt_chars=len(request.user_prompt),
        node_config_keys=sorted(request.node_config),
        backend=getattr(backend, "name", type(backend).__name__),
    )
    graph = _build_template_graph(
        default_workflow_template(), backend=backend, checkpointer=checkpointer
    )
    config = workflow_config(
        checkpointer=checkpointer, thread_id=request.thread_id.strip(), run_id=state["run_id"]
    )
    async for event in _stream_graph_values(
        graph=graph,
        input_value=state,
        config=config,
        started_at=started_at,
        log_context={
            "workflow_id": request.workflow_id,
            "thread_id": request.thread_id.strip(),
            "run_id": state["run_id"],
        },
    ):
        yield event


async def resume_workflow_thread(
    *,
    thread_id: str,
    decision: HumanDecision,
    backend,
    checkpointer,
) -> WorkflowRunResult:
    started_at = perf_counter()
    _require_hitl_checkpointer(checkpointer)
    if not thread_id.strip():
        raise ValueError("thread_id must not be empty")
    logger.info(
        "workflow.thread.resume_requested",
        thread_id=thread_id.strip(),
        node_id=decision.node_id,
        action=decision.action,
        patch_keys=sorted(decision.patch),
        has_choice=decision.choice is not None,
        backend=getattr(backend, "name", type(backend).__name__),
    )
    graph = _build_template_graph(
        default_workflow_template(), backend=backend, checkpointer=checkpointer
    )
    config = workflow_config(checkpointer=checkpointer, thread_id=thread_id.strip())
    try:
        result = await asyncio.to_thread(
            graph.invoke, Command(resume=decision.model_dump()), config
        )
        run_result = _run_result_from_state(result)
        logger.info(
            "workflow.thread.resume_completed",
            workflow_id=run_result.workflow_id,
            thread_id=thread_id.strip(),
            run_id=run_result.run_id,
            status=run_result.status,
            waiting_node_id=run_result.waiting.node_id if run_result.waiting else None,
            trace_node_count=len(run_result.trace.nodes),
            duration_ms=_elapsed_ms(started_at),
        )
        return run_result
    except Exception as exc:
        logger.exception(
            "workflow.thread.failed",
            thread_id=thread_id.strip(),
            node_id=decision.node_id,
            action=decision.action,
            error_type=type(exc).__name__,
            duration_ms=_elapsed_ms(started_at),
        )
        raise


async def stream_resume_workflow_thread(
    *,
    thread_id: str,
    decision: HumanDecision,
    backend,
    checkpointer,
) -> AsyncIterator[WorkflowStreamEvent]:
    started_at = perf_counter()
    _require_hitl_checkpointer(checkpointer)
    if not thread_id.strip():
        raise ValueError("thread_id must not be empty")
    logger.info(
        "workflow.thread.resume_stream_started",
        thread_id=thread_id.strip(),
        node_id=decision.node_id,
        action=decision.action,
        patch_keys=sorted(decision.patch),
        has_choice=decision.choice is not None,
        backend=getattr(backend, "name", type(backend).__name__),
    )
    graph = _build_template_graph(
        default_workflow_template(), backend=backend, checkpointer=checkpointer
    )
    config = workflow_config(checkpointer=checkpointer, thread_id=thread_id.strip())
    async for event in _stream_graph_values(
        graph=graph,
        input_value=Command(resume=decision.model_dump()),
        config=config,
        started_at=started_at,
        log_context={
            "thread_id": thread_id.strip(),
            "node_id": decision.node_id,
            "action": decision.action,
        },
    ):
        yield event


async def workflow_thread_trace(*, thread_id: str, checkpointer) -> WorkflowTrace:
    started_at = perf_counter()
    _require_hitl_checkpointer(checkpointer)
    if not thread_id.strip():
        raise ValueError("thread_id must not be empty")
    graph = _build_template_graph(
        default_workflow_template(), backend=None, checkpointer=checkpointer
    )
    snapshot = await asyncio.to_thread(
        graph.get_state,
        workflow_config(checkpointer=checkpointer, thread_id=thread_id.strip()),
    )
    values = dict(snapshot.values or {})
    trace = _trace_from_state(values, _waiting_from_interrupts(snapshot.interrupts))
    logger.info(
        "workflow.thread.trace_loaded",
        workflow_id=trace.workflow_id,
        thread_id=thread_id.strip(),
        run_id=trace.run_id,
        trace_node_count=len(trace.nodes),
        duration_ms=_elapsed_ms(started_at),
    )
    return trace


async def workflow_thread_result(*, thread_id: str, checkpointer) -> WorkflowRunResult:
    started_at = perf_counter()
    _require_hitl_checkpointer(checkpointer)
    if not thread_id.strip():
        raise ValueError("thread_id must not be empty")
    graph = _build_template_graph(
        default_workflow_template(), backend=None, checkpointer=checkpointer
    )
    snapshot = await asyncio.to_thread(
        graph.get_state,
        workflow_config(checkpointer=checkpointer, thread_id=thread_id.strip()),
    )
    values = dict(snapshot.values or {})
    waiting = _waiting_from_interrupts(snapshot.interrupts)
    trace = _trace_from_state(values, waiting)
    output = None if waiting else _creation_result_from_state(values)
    result = WorkflowRunResult(
        workflow_id=trace.workflow_id,
        thread_id=trace.thread_id,
        run_id=trace.run_id,
        status="waiting" if waiting else "completed",
        waiting=waiting,
        output=output,
        trace=trace,
    )
    logger.info(
        "workflow.thread.result_loaded",
        workflow_id=result.workflow_id,
        thread_id=thread_id.strip(),
        run_id=result.run_id,
        status=result.status,
        trace_node_count=len(result.trace.nodes),
        duration_ms=_elapsed_ms(started_at),
    )
    return result


def _build_template_graph(template: WorkflowDefinition, *, backend, checkpointer):
    _validate_workflow_definition(template)
    graph = StateGraph(WorkflowState)
    nodes = _TemplateNodeRegistry(template, backend)
    for node in template.nodes:
        graph.add_node(node.id, nodes.callable_for(node))
    graph.add_edge(START, template.start_node_id)
    for edge in template.edges:
        graph.add_edge(edge.source, edge.target)
    terminal_ids = _terminal_node_ids(template)
    if len(terminal_ids) != 1:
        raise ValueError("workflow definition must contain exactly one terminal node")
    graph.add_edge(terminal_ids[0], END)
    return graph.compile(checkpointer=checkpointer, name=template.workflow_id)


def _pro_stage_label(stage: str) -> str:
    label = PRO_STAGE_LABELS.get(stage)
    if label is None:
        raise ValueError(f"missing pro stage display label: {stage}")
    return label


def _require_hitl_checkpointer(checkpointer) -> None:
    if checkpointer is None:
        raise ValueError("HITL workflow requires a LangGraph checkpointer")


def _initial_workflow_state(request: WorkflowRunRequest, *, checkpointer) -> WorkflowState:
    _require_hitl_checkpointer(checkpointer)
    if request.workflow_id != default_workflow_template().workflow_id:
        raise ValueError(f"unsupported workflow_id: {request.workflow_id}")
    if not request.thread_id.strip():
        raise ValueError("thread_id must not be empty")
    return {
        "workflow_id": request.workflow_id,
        "workflow_version": default_workflow_template().version,
        "thread_id": request.thread_id.strip(),
        "run_id": f"run-{uuid4().hex}",
        "user_prompt": request.user_prompt,
        "music_dimensions": {},
        "skill_id": None,
        "prompt_pack": resolve_prompt_pack("pro_lyrics").to_state(),
        "node_config": request.node_config,
        "trace_nodes": [],
    }


async def _stream_graph_values(
    *,
    graph,
    input_value,
    config: dict[str, Any],
    started_at: float,
    log_context: dict[str, Any],
) -> AsyncIterator[WorkflowStreamEvent]:
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    latest_state: dict[str, Any] | None = None
    last_trace_count = 0

    def run_stream() -> None:
        try:
            for chunk in graph.stream(input_value, config, stream_mode=["values", "custom"]):
                if not isinstance(chunk, tuple) or len(chunk) != 2:
                    raise ValueError("workflow stream chunk must be a (mode, payload) tuple")
                mode, payload = chunk
                if mode == "values":
                    loop.call_soon_threadsafe(queue.put_nowait, ("state", dict(payload)))
                elif mode == "custom":
                    loop.call_soon_threadsafe(queue.put_nowait, ("custom", payload))
                else:
                    raise ValueError(f"unsupported workflow stream mode: {mode}")
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

    stream_thread = Thread(target=run_stream, name="yts-workflow-stream", daemon=True)
    stream_thread.start()

    try:
        while True:
            kind, payload = await queue.get()
            if kind == "done":
                break
            if kind == "error":
                raise payload
            if kind == "custom":
                yield _stream_event_from_custom_payload(payload)
                continue
            state = payload
            latest_state = state
            waiting = _interrupt_from_state(state)
            trace = _trace_from_state(state, waiting)
            if len(trace.nodes) > last_trace_count:
                last_trace_count = len(trace.nodes)
                yield WorkflowStreamEvent(type="trace", trace=trace)
        if latest_state is None:
            raise ValueError("workflow stream produced no state")
        result = _run_result_from_state(latest_state)
        logger.info(
            "workflow.thread.stream_completed",
            **log_context,
            status=result.status,
            waiting_node_id=result.waiting.node_id if result.waiting else None,
            trace_node_count=len(result.trace.nodes),
            duration_ms=_elapsed_ms(started_at),
        )
        yield WorkflowStreamEvent(type="result", result=result)
    except Exception as exc:
        logger.exception(
            "workflow.thread.stream_failed",
            **log_context,
            error_type=type(exc).__name__,
            duration_ms=_elapsed_ms(started_at),
        )
        raise


def _stream_event_from_custom_payload(payload: Any) -> WorkflowStreamEvent:
    if not isinstance(payload, dict):
        raise ValueError(
            f"workflow custom stream payload must be an object, got {type(payload).__name__}"
        )
    if payload.get("type") != "node_status":
        raise ValueError(f"unsupported workflow custom stream event: {payload.get('type')}")
    node_id = payload.get("node_id")
    status = payload.get("status")
    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("workflow node_status event requires node_id")
    if not isinstance(status, str) or not status.strip():
        raise ValueError("workflow node_status event requires status")
    attempt = payload.get("attempt")
    if attempt is not None and not isinstance(attempt, int):
        raise ValueError("workflow node_status event attempt must be an integer")
    detail = payload.get("detail")
    if detail is not None and not isinstance(detail, str):
        raise ValueError("workflow node_status event detail must be a string")
    return WorkflowStreamEvent(
        type="node_status",
        node_id=node_id,
        status=status,
        attempt=attempt,
        detail=detail,
    )


class _TemplateNodeRegistry:
    def __init__(self, template: WorkflowDefinition, backend) -> None:
        self.template = template
        self.backend = backend
        self.pro_nodes = ProLyricsNodes(backend) if backend is not None else None

    def callable_for(self, node: WorkflowNodeDefinition):
        if node.type == "pro_stage":
            return self._pro_stage(node)
        if node.type == "hitl_review":
            return self._final_review
        if node.type == "output":
            return self._done
        raise ValueError(f"unsupported workflow node type: {node.type}")

    def _pro_stage(self, node: WorkflowNodeDefinition):
        stage = node.config.get("stage")
        if not isinstance(stage, str) or not stage:
            raise ValueError(f"{node.id}.stage must be a non-empty string")
        if stage not in PRO_STAGE_ORDER:
            raise ValueError(f"unsupported pro stage: {stage}")

        def run_stage(state: WorkflowState) -> dict[str, Any]:
            if self.pro_nodes is None:
                raise ValueError(f"workflow pro stage {stage} requires backend")
            stage_fn = getattr(self.pro_nodes, stage, None)
            if not callable(stage_fn):
                raise ValueError(f"workflow pro stage {stage} is not callable")
            started_at = perf_counter()
            logger.info(
                "workflow.node.started",
                workflow_id=state.get("workflow_id"),
                thread_id=state.get("thread_id"),
                run_id=state.get("run_id"),
                node_id=node.id,
                node_type="pro_stage",
                stage=stage,
            )
            try:
                update = _run_pro_stage(
                    stage_fn,
                    state,
                    repair_event_sink=_current_stream_event_sink(),
                )
            except Exception as exc:
                logger.exception(
                    "workflow.node.failed",
                    workflow_id=state.get("workflow_id"),
                    thread_id=state.get("thread_id"),
                    run_id=state.get("run_id"),
                    node_id=node.id,
                    node_type="pro_stage",
                    stage=stage,
                    error_type=type(exc).__name__,
                    duration_ms=_elapsed_ms(started_at),
                )
                raise
            duration_ms = _elapsed_ms(started_at)
            logger.info(
                "workflow.node.completed",
                workflow_id=state.get("workflow_id"),
                thread_id=state.get("thread_id"),
                run_id=state.get("run_id"),
                node_id=node.id,
                node_type="pro_stage",
                stage=stage,
                update_keys=sorted(update),
                duration_ms=duration_ms,
            )
            update["trace_nodes"] = _append_trace(
                {**state, **update},
                node.id,
                "pro_stage",
                "completed",
                duration_ms=duration_ms,
            )
            if stage == "build_response":
                update["creation_result"] = _creation_result_payload({**state, **update})
            return update

        return run_stage

    def _final_review(self, state: WorkflowState) -> dict[str, Any]:
        creation_result = _creation_result_from_state(state)
        node_config = _node_config(state, "final_review")
        actions = _string_list_config(node_config, "final_review", "actions")
        editable_fields = _string_list_config(node_config, "final_review", "editable_fields")
        waiting = WaitingForHuman(
            node_id="final_review",
            kind="review",
            prompt="请评审生成的 Suno 成稿，接受、编辑或重新运行。",
            actions=actions,
            editable_fields=editable_fields,
            state_preview={
                "title": creation_result.title,
                "style": creation_result.style,
                "lyrics": creation_result.lyrics,
            },
        )
        logger.info(
            "workflow.hitl.waiting",
            workflow_id=state.get("workflow_id"),
            thread_id=state.get("thread_id"),
            run_id=state.get("run_id"),
            node_id=waiting.node_id,
            kind=waiting.kind,
            actions=actions,
            editable_fields=editable_fields,
        )
        decision = HumanDecision.model_validate(interrupt(waiting.model_dump()))
        logger.info(
            "workflow.hitl.decision",
            workflow_id=state.get("workflow_id"),
            thread_id=state.get("thread_id"),
            run_id=state.get("run_id"),
            node_id=decision.node_id,
            action=decision.action,
            patch_keys=sorted(decision.patch),
            has_choice=decision.choice is not None,
        )
        if decision.node_id != "final_review":
            raise ValueError("human decision node_id must match final_review")
        if decision.action == "rerun":
            raise ValueError("final review rerun is not enabled in locked template v1")
        started_at = perf_counter()
        result = creation_result
        if decision.action == "edit":
            result = creation_result.model_copy(update=decision.patch)
        return {
            "creation_result": result.model_dump(),
            "trace_nodes": _append_trace(
                state,
                "final_review",
                "hitl_review",
                "completed",
                duration_ms=_elapsed_ms(started_at),
            ),
        }

    def _done(self, state: WorkflowState) -> dict[str, Any]:
        started_at = perf_counter()
        return {
            "trace_nodes": _append_trace(
                state,
                "done",
                "output",
                "completed",
                duration_ms=_elapsed_ms(started_at),
            )
        }


def _node_config(state: WorkflowState, node_id: str) -> dict[str, Any]:
    template = default_workflow_template()
    base = next((node.config for node in template.nodes if node.id == node_id), None)
    if base is None:
        raise ValueError(f"unknown workflow node config: {node_id}")
    overrides = state.get("node_config", {}).get(node_id, {})
    if not isinstance(overrides, dict):
        raise ValueError(f"{node_id} config must be an object")
    return {**base, **overrides}


def _string_list_config(config: dict[str, Any], node_id: str, key: str) -> list[str]:
    value = config.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{node_id}.{key} must be a list of strings")
    return value


def _creation_result_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": state.get("title", ""),
        "lyrics": state.get("lyrics", ""),
        "style": state.get("style", ""),
        "final_draft": state.get("final_draft", ""),
        "summary": {
            "prompt_pack": state["prompt_pack"],
            "stages": [
                stage.model_dump() if hasattr(stage, "model_dump") else stage
                for stage in state.get("stages", [])
            ],
        },
    }


def _run_result_from_state(state: dict[str, Any]) -> WorkflowRunResult:
    waiting = _interrupt_from_state(state)
    trace = _trace_from_state(state, waiting)
    output = None if waiting else _creation_result_from_state(state)
    return WorkflowRunResult(
        workflow_id=state["workflow_id"],
        thread_id=state["thread_id"],
        run_id=state["run_id"],
        status="waiting" if waiting else "completed",
        waiting=waiting,
        output=output,
        trace=trace,
    )


def _trace_from_state(state: dict[str, Any], waiting: WaitingForHuman | None) -> WorkflowTrace:
    nodes = [WorkflowTraceNode.model_validate(node) for node in state.get("trace_nodes", [])]
    if waiting is not None:
        nodes.append(
            WorkflowTraceNode(
                node_id=waiting.node_id,
                span_id=_trace_span_id(state, waiting.node_id),
                duration_ms=0,
                node_type=f"hitl_{waiting.kind}",
                status="waiting",
                summary=waiting.prompt,
                artifact_preview=waiting.state_preview,
                llm_call=None,
            )
        )
    return WorkflowTrace(
        workflow_id=str(state.get("workflow_id", default_workflow_template().workflow_id)),
        workflow_version=int(state.get("workflow_version", default_workflow_template().version)),
        thread_id=str(state.get("thread_id", "")),
        run_id=str(state.get("run_id", "")),
        nodes=nodes,
    )


def _interrupt_from_state(state: dict[str, Any]) -> WaitingForHuman | None:
    interrupts = state.get("__interrupt__")
    return _waiting_from_interrupts(interrupts)


def _waiting_from_interrupts(interrupts: Any) -> WaitingForHuman | None:
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    return WaitingForHuman.model_validate(value)


def _creation_result_from_state(state: dict[str, Any]) -> CreationResult:
    payload = state.get("creation_result")
    if not isinstance(payload, dict):
        raise ValueError("workflow state missing creation_result")
    return CreationResult.model_validate(payload)


def _validate_workflow_definition(template: WorkflowDefinition) -> None:
    node_ids = [node.id for node in template.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("workflow definition contains duplicate node ids")
    if template.start_node_id not in node_ids:
        raise ValueError("workflow start_node_id must reference a node")
    node_id_set = set(node_ids)
    for edge in template.edges:
        if edge.source not in node_id_set:
            raise ValueError(f"workflow edge source is unknown: {edge.source}")
        if edge.target not in node_id_set:
            raise ValueError(f"workflow edge target is unknown: {edge.target}")
    pro_stage_ids = [node.id for node in template.nodes if node.type == "pro_stage"]
    missing = [stage for stage in PRO_STAGE_ORDER if stage not in pro_stage_ids]
    if missing:
        raise ValueError(f"workflow missing required pro stages: {', '.join(missing)}")


def _terminal_node_ids(template: WorkflowDefinition) -> list[str]:
    sources = {edge.source for edge in template.edges}
    return [node.id for node in template.nodes if node.id not in sources]


def _run_pro_stage(
    stage_fn: Callable[..., Awaitable[dict[str, Any]]],
    state: WorkflowState,
    *,
    repair_event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    loop = _pro_stage_event_loop()
    future = asyncio.run_coroutine_threadsafe(
        stage_fn(state, repair_event_sink=repair_event_sink),
        loop,
    )
    return _pro_stage_result(future)


def _current_stream_event_sink() -> Callable[[dict[str, Any]], None] | None:
    try:
        return get_stream_writer()
    except RuntimeError:
        return None


def _pro_stage_result(future: Future) -> dict[str, Any]:
    result = future.result()
    if not isinstance(result, dict):
        raise TypeError(f"workflow pro stage must return dict, got {type(result).__name__}")
    return result


def _pro_stage_event_loop() -> asyncio.AbstractEventLoop:
    global _PRO_STAGE_LOOP, _PRO_STAGE_LOOP_THREAD

    with _PRO_STAGE_LOOP_LOCK:
        if (
            _PRO_STAGE_LOOP is not None
            and _PRO_STAGE_LOOP_THREAD is not None
            and _PRO_STAGE_LOOP_THREAD.is_alive()
            and not _PRO_STAGE_LOOP.is_closed()
        ):
            return _PRO_STAGE_LOOP

        loop_ready: Future[asyncio.AbstractEventLoop] = Future()

        def run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_ready.set_result(loop)
            loop.run_forever()

        thread = Thread(target=run_loop, name="yts-pro-stage-llm-loop", daemon=True)
        thread.start()
        _PRO_STAGE_LOOP = loop_ready.result()
        _PRO_STAGE_LOOP_THREAD = thread
        return _PRO_STAGE_LOOP


def _append_trace(
    state: WorkflowState,
    node_id: str,
    node_type: str,
    status: Literal["completed", "waiting", "pending"],
    *,
    duration_ms: int,
    stage_count: int = 0,
    note: str | None = None,
) -> list[dict[str, Any]]:
    nodes = list(state.get("trace_nodes", []))
    nodes.append(
        WorkflowTraceNode(
            node_id=node_id,
            node_type=node_type,
            status=status,
            duration_ms=duration_ms,
            stage_count=stage_count,
            note=note,
            summary=_trace_summary(state, node_id),
            artifact_preview=_trace_artifact_preview(state, node_id),
            metrics=_trace_metrics(state, node_id),
            span_id=_trace_span_id(state, node_id),
            llm_call=_trace_llm_call(state, node_id),
        ).model_dump()
    )
    return nodes


def _elapsed_ms(started_at: float) -> int:
    return max(0, int(round((perf_counter() - started_at) * 1000)))


def _trace_span_id(state: dict[str, Any], node_id: str) -> str:
    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("workflow state missing run_id for trace span")
    return f"{run_id.strip()}:{node_id}"


def _trace_llm_call(state: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    calls = state.get("llm_calls", {})
    if not isinstance(calls, dict):
        raise ValueError("workflow state llm_calls must be an object")
    value = calls.get(node_id)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"workflow trace {node_id} llm_call must be an object")
    return value


def _trace_summary(state: dict[str, Any], node_id: str) -> str:
    preview = _trace_artifact_preview(state, node_id)
    if node_id == "validate_request":
        return str(state.get("user_prompt", ""))[:40]
    if node_id == "parse_intent":
        return _join_preview(preview.get("emotion_cues") or preview.get("scene_cues"))
    if node_id == "build_song_brief":
        return str(preview.get("core_story") or "")
    if node_id == "plan_music_style":
        return str(preview.get("selected_label") or preview.get("selected_style_id") or "")
    if node_id == "hook_lab":
        return str(preview.get("selected_hook") or "")
    if node_id == "draft_structure_blueprints":
        return f"{preview.get('blueprint_count', 0)} 个结构候选"
    if node_id == "critique_structure":
        return str(preview.get("selected_blueprint_id") or "")
    if node_id == "plan_style_prompt":
        return str(preview.get("style_prompt") or "")[:80]
    if node_id in {"generate_lyrics", "normalize_suno_format"}:
        return str(preview.get("title") or "")
    if node_id == "review_quality":
        return f"{preview.get('decision', '')} / {preview.get('overall_score', '')}".strip(" /")
    if node_id == "repair_lyrics":
        return "无需修复" if not preview.get("repair_attempted") else "已修复"
    if node_id == "refine_title":
        return str(preview.get("final_title") or "")
    if node_id == "build_response":
        return str(preview.get("title") or "")
    return ""


def _trace_artifact_preview(state: dict[str, Any], node_id: str) -> dict[str, Any]:
    if node_id == "validate_request":
        return {"user_prompt": state.get("user_prompt", "")}
    if node_id == "parse_intent":
        intent = _require_trace_mapping(state, node_id, "intent")
        return {
            "scene_cues": _preview_list(intent.get("scene_cues")),
            "emotion_cues": _preview_list(intent.get("emotion_cues")),
            "style_cues": _preview_list(intent.get("style_cues")),
        }
    if node_id == "build_song_brief":
        brief = _require_trace_mapping(state, node_id, "song_brief")
        return {
            "core_story": brief.get("core_story", ""),
            "emotion_arc": _preview_list(brief.get("emotion_arc")),
            "target_form": brief.get("target_form", ""),
        }
    if node_id == "plan_music_style":
        plan = _require_trace_mapping(state, node_id, "music_style_plan")
        selected = _require_trace_child_mapping(plan, node_id, "music_style_plan.selected_style")
        return {
            "selected_style_id": plan.get("selected_style_id", ""),
            "selected_label": selected.get("label", ""),
            "selected_template_id": selected.get("template_id", ""),
            "bpm_range": selected.get("bpm_range", {}),
            "vocal_profile": selected.get("vocal_profile", ""),
            "instrumentation": _preview_list(selected.get("instrumentation")),
            "negative_tags": _preview_list(plan.get("negative_tags")),
        }
    if node_id == "hook_lab":
        hook = _require_trace_mapping(state, node_id, "hook_lab")
        return {
            "selected_hook": hook.get("selected_hook", ""),
            "hook_strategy": hook.get("hook_strategy", ""),
            "candidates": _preview_list(hook.get("candidates"), limit=3),
        }
    if node_id == "draft_structure_blueprints":
        structure_blueprints = _require_trace_mapping(state, node_id, "structure_blueprints")
        blueprints = _preview_list(structure_blueprints.get("blueprints"), limit=3)
        return {
            "blueprint_count": len(
                _require_trace_list(
                    structure_blueprints.get("blueprints"),
                    node_id,
                    "structure_blueprints.blueprints",
                )
            ),
            "blueprints": [
                {
                    "id": item.get("id", ""),
                    "mode": item.get("mode", ""),
                    "sections": _preview_list(item.get("sections"), limit=8),
                }
                for item in blueprints
                if isinstance(item, dict)
            ],
        }
    if node_id == "critique_structure":
        critique = _require_trace_mapping(state, node_id, "structure_critique")
        professional_plan = _require_trace_mapping(state, node_id, "professional_plan")
        selected = _require_trace_child_mapping(
            professional_plan, node_id, "professional_plan.selected_blueprint"
        )
        return {
            "selected_blueprint_id": critique.get("selected_blueprint_id")
            or selected.get("id", ""),
            "critic_notes": _preview_list(critique.get("critic_notes")),
            "sections": _preview_list(selected.get("sections"), limit=8),
        }
    if node_id == "plan_style_prompt":
        spec = _require_trace_mapping(state, node_id, "style_spec")
        family = _require_trace_child_mapping(spec, node_id, "style_spec.style_family")
        return {
            "style_family": family,
            "style_prompt": spec.get("style_prompt_draft", ""),
            "style_components": _preview_list(spec.get("style_components"), limit=8),
            "negative_terms": _preview_list(spec.get("negative_terms")),
        }
    if node_id in {"generate_lyrics", "normalize_suno_format"}:
        generation = _require_trace_mapping(state, node_id, "generation")
        return {
            "title": generation.get("title", ""),
            "style_prompt": generation.get("style_prompt", ""),
            "hook": generation.get("hook", ""),
            "structure": _preview_list(generation.get("structure"), limit=10),
            "lyric_excerpt": str(generation.get("lyric_prompt", ""))[:240],
        }
    if node_id == "review_quality":
        review = _require_trace_mapping(state, node_id, "quality_review")
        return {
            "decision": review.get("decision", ""),
            "overall_score": review.get("overall_score", ""),
            "main_issues": _preview_list(review.get("main_issues")),
            "suggestions": _preview_list(review.get("suggestions")),
        }
    if node_id == "repair_lyrics":
        review = _require_trace_mapping(state, node_id, "quality_review")
        return {
            "repair_attempted": bool(review.get("repair_attempted", False)),
            "repair_succeeded": bool(review.get("repair_succeeded", False)),
        }
    if node_id == "refine_title":
        title = _require_trace_mapping(state, node_id, "title_refinement")
        return {
            "original_title": title.get("original_title", ""),
            "final_title": title.get("final_title", ""),
            "selection_reason": title.get("selection_reason", ""),
        }
    if node_id == "build_response":
        return {
            "title": state.get("title", ""),
            "style": state.get("style", ""),
            "lyrics_excerpt": str(state.get("lyrics", ""))[:240],
        }
    return {}


def _trace_metrics(state: dict[str, Any], node_id: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if node_id == "plan_music_style":
        candidates = _require_trace_mapping(state, node_id, "music_style_plan").get(
            "style_candidates", []
        )
        metrics["candidate_count"] = len(candidates) if isinstance(candidates, list) else 0
    elif node_id == "hook_lab":
        candidates = _require_trace_mapping(state, node_id, "hook_lab").get("candidates", [])
        metrics["candidate_count"] = len(candidates) if isinstance(candidates, list) else 0
    elif node_id == "draft_structure_blueprints":
        blueprints = _require_trace_mapping(state, node_id, "structure_blueprints").get(
            "blueprints", []
        )
        metrics["candidate_count"] = len(blueprints) if isinstance(blueprints, list) else 0
    elif node_id == "generate_lyrics":
        lyrics = str(_require_trace_mapping(state, node_id, "generation").get("lyric_prompt", ""))
        metrics["lyric_chars"] = len(lyrics)
    repairs = state.get("node_repairs", {})
    if not isinstance(repairs, dict):
        raise ValueError("workflow state node_repairs must be an object")
    repair_attempts = repairs.get(node_id, [])
    if repair_attempts:
        if not isinstance(repair_attempts, list):
            raise ValueError(f"workflow trace {node_id} node_repairs must be a list")
        metrics["repaired"] = True
        metrics["repair_attempt_count"] = len(repair_attempts)
        metrics["repair_errors"] = [
            str(attempt.get("validation_error", ""))
            for attempt in repair_attempts
            if isinstance(attempt, dict)
        ]
    return metrics


def _require_trace_mapping(state: dict[str, Any], node_id: str, key: str) -> dict[str, Any]:
    value = state.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"workflow trace {node_id} requires state.{key} to be an object")
    return value


def _require_trace_child_mapping(parent: dict[str, Any], node_id: str, key: str) -> dict[str, Any]:
    child_key = key.rsplit(".", 1)[-1]
    value = parent.get(child_key)
    if not isinstance(value, dict):
        raise ValueError(f"workflow trace {node_id} requires state.{key} to be an object")
    return value


def _require_trace_list(value: Any, node_id: str, key: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"workflow trace {node_id} requires state.{key} to be a list")
    return value


def _preview_list(value: Any, *, limit: int = 5) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


def _join_preview(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return "、".join(str(item) for item in value[:3] if str(item).strip())
