from __future__ import annotations

import pytest
from yts_core.inference import TextResult
from yts_core.orchestration.flows.pro_lyrics import PRO_STAGE_ORDER
from yts_core.workflow.runtime import (
    HumanDecision,
    WorkflowRunRequest,
    _append_trace,
    default_workflow_template,
    resume_workflow_thread,
    run_workflow_thread,
    workflow_thread_trace,
)


@pytest.mark.asyncio
async def test_locked_template_exposes_future_editable_dag_shape() -> None:
    template = default_workflow_template()

    assert template.workflow_id == "pro_creation_hitl_v1"
    assert template.capabilities.locked_edges is True
    expected_nodes = [
        "validate_request",
        "parse_intent",
        "build_song_brief",
        "brief_approval",
        "plan_music_style",
        "hook_lab",
        "draft_structure_blueprints",
        "critique_structure",
        "plan_style_prompt",
        "generate_lyrics",
        "review_quality",
        "repair_lyrics",
        "normalize_suno_format",
        "refine_title",
        "build_response",
        "final_review",
        "done",
    ]
    assert [node.id for node in template.nodes] == expected_nodes
    assert [(edge.source, edge.target) for edge in template.edges] == [
        ("validate_request", "parse_intent"),
        ("parse_intent", "build_song_brief"),
        ("build_song_brief", "brief_approval"),
        ("brief_approval", "plan_music_style"),
        ("plan_music_style", "hook_lab"),
        ("hook_lab", "draft_structure_blueprints"),
        ("draft_structure_blueprints", "critique_structure"),
        ("critique_structure", "plan_style_prompt"),
        ("plan_style_prompt", "generate_lyrics"),
        ("generate_lyrics", "review_quality"),
        ("review_quality", "repair_lyrics"),
        ("repair_lyrics", "normalize_suno_format"),
        ("normalize_suno_format", "refine_title"),
        ("refine_title", "build_response"),
        ("build_response", "final_review"),
        ("final_review", "done"),
    ]
    assert template.start_node_id == "validate_request"
    assert [node.id for node in template.nodes if node.type == "pro_stage"] == list(PRO_STAGE_ORDER)
    assert template.nodes[3].type == "hitl_approval"
    assert template.nodes[-2].type == "hitl_review"


@pytest.mark.asyncio
async def test_workflow_thread_run_waits_at_brief_approval() -> None:
    runtime = WorkflowHarness()

    result = await run_workflow_thread(
        WorkflowRunRequest(
            workflow_id="pro_creation_hitl_v1",
            thread_id="thread-brief",
            user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
        ),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    assert result.status == "waiting"
    assert result.waiting.node_id == "brief_approval"
    assert result.waiting.kind == "approval"
    assert result.thread_id == "thread-brief"
    assert [node.node_id for node in result.trace.nodes[:4]] == [
        "validate_request",
        "parse_intent",
        "build_song_brief",
        "brief_approval",
    ]
    assert result.trace.nodes[-1].node_id == "brief_approval"
    assert result.trace.nodes[-1].status == "waiting"


@pytest.mark.asyncio
async def test_workflow_thread_uses_editable_node_config_for_waiting_prompt() -> None:
    runtime = WorkflowHarness()

    result = await run_workflow_thread(
        WorkflowRunRequest(
            workflow_id="pro_creation_hitl_v1",
            thread_id="thread-node-config",
            user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
            node_config={
                "brief_approval": {
                    "actions": ["approve", "reject"],
                    "editable_fields": ["user_prompt"],
                }
            },
        ),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    assert result.waiting.actions == ["approve", "reject"]
    assert result.waiting.editable_fields == ["user_prompt"]


@pytest.mark.asyncio
async def test_workflow_thread_rejects_invalid_node_config_shape() -> None:
    runtime = WorkflowHarness()

    with pytest.raises(ValueError, match="brief_approval.actions must be a list of strings"):
        await run_workflow_thread(
            WorkflowRunRequest(
                workflow_id="pro_creation_hitl_v1",
                thread_id="thread-bad-node-config",
                user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
                node_config={"brief_approval": {"actions": "approve"}},
            ),
            backend=runtime.backend,
            checkpointer=runtime.checkpointer,
        )


@pytest.mark.asyncio
async def test_workflow_thread_requires_checkpointer_for_hitl() -> None:
    runtime = WorkflowHarness()

    with pytest.raises(ValueError, match="requires a LangGraph checkpointer"):
        await run_workflow_thread(
            WorkflowRunRequest(
                workflow_id="pro_creation_hitl_v1",
                thread_id="thread-no-checkpointer",
                user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
            ),
            backend=runtime.backend,
            checkpointer=None,
        )


@pytest.mark.asyncio
async def test_workflow_thread_resume_runs_to_final_review() -> None:
    runtime = WorkflowHarness()
    await run_workflow_thread(
        WorkflowRunRequest(
            workflow_id="pro_creation_hitl_v1",
            thread_id="thread-final",
            user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
        ),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    result = await resume_workflow_thread(
        thread_id="thread-final",
        decision=HumanDecision(node_id="brief_approval", action="approve"),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    assert result.status == "waiting"
    assert result.waiting.node_id == "final_review"
    assert result.output is None
    trace_node_ids = [node.node_id for node in result.trace.nodes]
    assert "generate_lyrics" in trace_node_ids
    assert "build_response" in trace_node_ids


@pytest.mark.asyncio
async def test_workflow_trace_nodes_include_artifact_previews_for_workspace() -> None:
    runtime = WorkflowHarness()
    await run_workflow_thread(
        WorkflowRunRequest(
            workflow_id="pro_creation_hitl_v1",
            thread_id="thread-artifacts",
            user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
        ),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    result = await resume_workflow_thread(
        thread_id="thread-artifacts",
        decision=HumanDecision(node_id="brief_approval", action="approve"),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    by_id = {node.node_id: node for node in result.trace.nodes}
    assert by_id["build_song_brief"].summary == "雨中想起远方故人"
    assert by_id["build_song_brief"].artifact_preview["core_story"] == "雨中想起远方故人"
    assert by_id["plan_music_style"].summary == "华语抒情流行"
    assert by_id["plan_music_style"].artifact_preview["selected_template_id"] == "mandarin_pop_ballad"
    assert by_id["hook_lab"].summary == "雨落旧窗前"
    assert by_id["generate_lyrics"].artifact_preview["title"] == "雨中旧窗"
    assert by_id["build_response"].artifact_preview["title"] == "雨中故人"
    assert all(node.span_id for node in result.trace.nodes)
    assert by_id["build_song_brief"].span_id == f"{result.trace.run_id}:build_song_brief"
    assert all(isinstance(node.duration_ms, int) for node in result.trace.nodes)
    assert all(node.duration_ms >= 0 for node in result.trace.nodes)
    assert by_id["validate_request"].llm_call is None
    assert by_id["parse_intent"].llm_call is not None
    assert by_id["parse_intent"].llm_call["provider"] == "fake"
    assert by_id["parse_intent"].llm_call["model"] == "fake"
    assert by_id["parse_intent"].llm_call["response_text"].startswith("{")
    assert by_id["parse_intent"].llm_call["parsed_json"]["emotion_cues"] == ["思念", "怀旧"]
    assert [message["role"] for message in by_id["parse_intent"].llm_call["input_messages"]] == [
        "system",
        "user",
    ]


def test_workflow_trace_preview_fails_when_stage_artifact_is_missing() -> None:
    state = {
        "trace_nodes": [],
        "music_style_plan": {
            "style_candidates": [],
            "selected_style_id": "mainstream_pop",
            "negative_tags": [],
        },
    }

    with pytest.raises(ValueError, match=r"plan_music_style.*selected_style"):
        _append_trace(state, "plan_music_style", "pro_stage", "completed", duration_ms=1)


@pytest.mark.asyncio
async def test_workflow_thread_resume_accepts_structured_hook_placement() -> None:
    runtime = WorkflowHarness()
    blueprints = runtime.backend.payloads["draft_structure_blueprints"]
    blueprints["blueprints"][0]["hook_placement"] = {
        "first_appearance": "Chorus1",
        "repeat_sections": ["Final Chorus"],
        "strategy": "selected_hook opens the chorus and returns at the final peak.",
    }
    blueprints["blueprints"][1]["hook_placement"] = {
        "first_appearance": "Chorus",
        "repeat_sections": ["Final Chorus"],
        "strategy": "selected_hook anchors both chorus payoffs.",
    }
    await run_workflow_thread(
        WorkflowRunRequest(
            workflow_id="pro_creation_hitl_v1",
            thread_id="thread-structured-hook",
            user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
        ),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    result = await resume_workflow_thread(
        thread_id="thread-structured-hook",
        decision=HumanDecision(node_id="brief_approval", action="approve"),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    assert result.status == "waiting"
    assert result.waiting.node_id == "final_review"
    trace_node_ids = [node.node_id for node in result.trace.nodes]
    assert "draft_structure_blueprints" in trace_node_ids
    assert "critique_structure" in trace_node_ids


@pytest.mark.asyncio
async def test_workflow_thread_accepts_final_review_and_returns_output() -> None:
    runtime = WorkflowHarness()
    await run_workflow_thread(
        WorkflowRunRequest(
            workflow_id="pro_creation_hitl_v1",
            thread_id="thread-done",
            user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
        ),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )
    await resume_workflow_thread(
        thread_id="thread-done",
        decision=HumanDecision(node_id="brief_approval", action="approve"),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    result = await resume_workflow_thread(
        thread_id="thread-done",
        decision=HumanDecision(node_id="final_review", action="accept"),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    assert result.status == "completed"
    assert result.waiting is None
    assert result.output.title == "雨中故人"
    assert result.output.summary.prompt_pack["pack_id"] == "pro_lyrics"
    assert result.output.summary.prompt_pack["version"]
    assert result.output.summary.prompt_pack["sha256"]
    assert "Style Prompt:" in result.output.final_draft


@pytest.mark.asyncio
async def test_workflow_thread_trace_reads_checkpoint_state() -> None:
    runtime = WorkflowHarness()
    await run_workflow_thread(
        WorkflowRunRequest(
            workflow_id="pro_creation_hitl_v1",
            thread_id="thread-trace",
            user_prompt="下雨的午后，大雨倾盆，思念远方的故人",
        ),
        backend=runtime.backend,
        checkpointer=runtime.checkpointer,
    )

    trace = await workflow_thread_trace(
        thread_id="thread-trace",
        checkpointer=runtime.checkpointer,
    )

    assert trace.thread_id == "thread-trace"
    assert trace.nodes[0].node_id == "validate_request"
    assert trace.nodes[-1].node_id == "brief_approval"
    assert trace.nodes[-1].status == "waiting"


class WorkflowHarness:
    def __init__(self) -> None:
        from langgraph.checkpoint.memory import InMemorySaver

        self.backend = _FakeProBackend()
        self.checkpointer = InMemorySaver()


class _FakeProBackend:
    name = "fake-pro"

    def __init__(self) -> None:
        from copy import deepcopy

        from test_creation_graph_pro import _PAYLOADS

        self.payloads = deepcopy(_PAYLOADS)
        self.payloads["review_quality"]["submit_suno"] = True

    async def generate_text(self, messages, *, model=None, fallbacks=None, response_format=None) -> TextResult:
        import json

        marker = "YTS_PRO_STAGE:"
        content = messages[-1]["content"]
        stage = content.split(marker, 1)[1].splitlines()[0].strip()
        return TextResult(text=json.dumps(self.payloads[stage], ensure_ascii=False), provider="fake", model="fake")
