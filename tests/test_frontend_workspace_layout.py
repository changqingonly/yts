from __future__ import annotations

from pathlib import Path

WORKFLOW_SOURCE = Path("desktop/frontend/src/pages/CreationPage.vue")


def test_frontend_defaults_to_workspace_before_flow_canvas() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert 'centerTab = ref("workspace")' in source
    assert "工作台" in source
    assert "v-if=\"centerTab === 'workspace'\"" in source
    assert "v-if=\"centerTab === 'canvas'\"" in source


def test_frontend_workspace_prioritizes_trace_artifacts_over_dag_io() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "artifact_preview" in source
    assert "artifactRows" in source
    assert "节点产物" in source
    assert "finalDelivery" in source
    assert "final-delivery" in source
    assert '<div class="section-label">Phoenix Trace</div>' not in source
    assert '<div class="section-label">输入输出</div>' not in source


def test_frontend_workspace_uses_diagnostic_three_pane_core() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "diagnostic-core" in source
    assert "diagnostic-main" in source
    assert "diagnostic-side" in source
    assert "LLM 输入" in source
    assert "LLM 输出" in source
    assert "llmCall" in source
    assert "llmInputPreview" in source
    assert "llmOutputPreview" in source
    assert "暂无调用记录" in source
    assert "nodeArtifactTitle" in source


def test_frontend_llm_panels_format_json_explicitly() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "function formatJsonPreview(value, label)" in source
    assert "JSON.stringify(parsed, null, 2)" in source
    assert "不是合法 JSON，无法格式化" in source
    assert "json-chip" in source
    assert "已格式化 JSON" in source
    assert "JSON 无效" in source
    assert "invalid-json" in source
    assert 'formatJsonPreview(llmCall.value.response_text, "LLM 输出")' in source


def test_frontend_llm_panels_do_not_stretch_preview_blocks() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    diagnostic_side_rule = source.rsplit(".diagnostic-side {", 1)[1].split("}", 1)[0]
    llm_panel_rule = source.split(".llm-panel {", 1)[1].split("}", 1)[0]
    llm_code_rule = source.rsplit(".llm-code {", 1)[1].split("}", 1)[0]

    assert "grid-template-rows: repeat(2, minmax(0, max-content));" in diagnostic_side_rule
    assert "grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);" not in diagnostic_side_rule
    assert "grid-template-rows: auto max-content;" in llm_panel_rule
    assert "height: max-content;" in llm_panel_rule
    assert "grid-template-rows: auto minmax(0, 1fr);" not in llm_panel_rule
    assert "max-height: min(38vh, 420px);" in llm_code_rule


def test_frontend_workspace_uses_compact_trace_focus_header() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "compact-focus-bar" in source
    assert "focusTraceIds.rootId" in source
    assert "focusTraceIds.spanId" in source
    assert "focusDurationLabel" in source
    assert "overview-chipline" in source
    assert '<div class="section-label">操作焦点</div>' not in source
    assert '<div class="section-label">运行概览</div>' not in source
    assert 'class="workspace-grid"' not in source


def test_frontend_selected_node_overrides_executing_focus_when_user_clicks_history_node() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    focus_node_id_body = source.split("const focusNodeId = computed(() => {", 1)[1].split(
        "\n});", 1
    )[0]
    select_node_body = source.split("function selectNode(nodeId) {", 1)[1].split("\n}", 1)[0]

    assert 'const userSelectedNodeId = ref("");' in source
    assert "if (userSelectedNodeId.value) return userSelectedNodeId.value;" in focus_node_id_body
    assert (
        "return currentExecutingNodeId.value || waitingNodeId.value || selectedNodeId.value;"
        in focus_node_id_body
    )
    assert "userSelectedNodeId.value = nodeId;" in select_node_body


def test_frontend_creation_page_reacts_to_global_api_target_changes() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "API_TARGET_CHANGED_EVENT" in source
    assert 'import { useEnvironmentStore } from "../stores/environment";' in source
    assert "const environment = useEnvironmentStore();" in source
    assert "function handleApiTargetChanged()" in source
    assert "runResult.value = null;" in source
    assert "trace.value = null;" in source
    assert "result.value = null;" in source
    assert "window.addEventListener(API_TARGET_CHANGED_EVENT, handleApiTargetChanged)" in source
    assert "window.removeEventListener(API_TARGET_CHANGED_EVENT, handleApiTargetChanged)" in source
    assert "void loadTemplate();" in source


def test_frontend_creation_page_locks_environment_switch_while_workflow_is_busy() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "environment.setSwitchLocked(isWorkflowBusy.value);" in source
    assert "const isWorkflowBusy = computed(() =>" in source
    assert 'status.value !== "idle"' in source
    assert 'runResult.value?.status === "waiting"' in source
    assert "environment.setSwitchLocked(false);" in source


def test_frontend_workspace_removes_boxy_outer_panel_borders() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    workspace_shell_rule = source.split(".workspace-card,\n.canvas-card {", 1)[1].split("}", 1)[0]
    compact_focus_rule = source.split(".compact-focus-bar {", 1)[1].split("}", 1)[0]
    workspace_panel_rule = source.split(".workspace-panel {", 1)[1].split("}", 1)[0]
    workspace_note_rule = source.split(".workspace-note {", 1)[1].split("}", 1)[0]

    for rule in [
        workspace_shell_rule,
        compact_focus_rule,
        workspace_panel_rule,
        workspace_note_rule,
    ]:
        assert "border:" not in rule
    assert "background: transparent;" in workspace_shell_rule
    assert "box-shadow:" in compact_focus_rule
    assert "box-shadow:" in workspace_panel_rule


def test_frontend_flow_navigation_is_grouped_by_workflow_stage() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "const flowGroups = computed(() =>" in source
    assert "flow-stage-group" in source
    assert "flow-stage-label" in source
    assert "group.nodes" in source
    assert "brief_approval" not in source
    assert "final_review" in source


def test_frontend_flow_navigation_scrollbar_does_not_cover_node_meta() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    compact_list_rule = source.split(".compact-list {", 1)[1].split("}", 1)[0]

    assert "scrollbar-gutter: stable;" in compact_list_rule
    assert "overflow-x: hidden;" in compact_list_rule
    assert "overflow-y: auto;" in compact_list_rule
    assert "padding-right: var(--timeline-scrollbar-safe-zone);" in compact_list_rule
    assert ".compact-list::-webkit-scrollbar" in source


def test_frontend_global_target_selector_is_not_duplicated_in_creation_toolbar() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "target-menu compact-target" not in source
    assert "const bases = {" not in source
    assert ".compact-target select" not in source
    assert ".compact-target span" not in source


def test_frontend_workflow_target_uses_global_selected_api_target() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "selectedApiTarget" in source
    assert "function workflowTarget()" in source
    assert "return selectedApiTarget();" in source
    assert "openJsonStream" in source


def test_frontend_workflow_blocks_network_calls_when_selected_target_is_offline() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    load_template_body = source.split("async function loadTemplate() {", 1)[1].split("\n}", 1)[0]
    run_thread_body = source.split("async function runThread() {", 1)[1].split("\n}", 1)[0]
    resume_thread_body = source.split("async function resumeThread(action) {", 1)[1].split(
        "\n}", 1
    )[0]
    refresh_trace_body = source.split("async function refreshTrace() {", 1)[1].split("\n}", 1)[0]
    load_history_body = source.split("async function loadHistoryItems() {", 1)[1].split("\n}", 1)[0]
    select_history_body = source.split("async function selectHistoryItem(item) {", 1)[1].split(
        "\n}", 1
    )[0]
    save_asset_body = source.split("async function saveFinalDeliveryToAssets() {", 1)[1].split(
        "\n}", 1
    )[0]

    assert "async function ensureWorkflowTargetOnline()" in source
    assert "function workflowTargetLabel(target = workflowTarget())" in source
    assert "function targetUnavailableMessage(target = workflowTarget())" in source
    assert "environment.targetHealth(target)" in source
    assert "await environment.checkHealth(target)" in source
    assert "throw new Error(targetUnavailableMessage(target));" in source
    assert "服务未连接，无法继续工作流操作" in source

    assert load_template_body.index(
        "await ensureWorkflowTargetOnline();"
    ) < load_template_body.index("requestWorkflowJson(`/api/workflows/${workflowId}/template`")
    assert run_thread_body.index("await ensureWorkflowTargetOnline();") < run_thread_body.index(
        "await streamWorkflow(`/api/workflows/${workflowId}/threads/stream`"
    )
    assert resume_thread_body.index(
        "await ensureWorkflowTargetOnline();"
    ) < resume_thread_body.index(
        "await streamWorkflow(`/api/workflows/${workflowId}/threads/${threadId.value}/stream`"
    )
    assert refresh_trace_body.index(
        "await ensureWorkflowTargetOnline();"
    ) < refresh_trace_body.index(
        "requestWorkflowJson(`/api/workflows/${workflowId}/threads/${threadId.value}/trace`"
    )
    assert load_history_body.index("await ensureWorkflowTargetOnline();") < load_history_body.index(
        "listWorkflowHistory(workflowId"
    )
    assert select_history_body.index(
        "await ensureWorkflowTargetOnline();"
    ) < select_history_body.index("getWorkflowTrace(workflowId")
    assert save_asset_body.index("await ensureWorkflowTargetOnline();") < save_asset_body.index(
        "saveSong({"
    )


def test_frontend_trace_details_live_in_drawer_only() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "node.summary || traceTypeLabel(node.node_type)" in source
    assert "formatDuration(node.duration_ms)" in source
    assert "drawerMode === 'trace'" in source
    assert "暂无节点产物" in source
    assert "traceEventNodes" not in source
    assert "span-list" not in source


def test_frontend_node_durations_are_visible_in_core_workflow_surfaces() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "function formatDuration(durationMs)" in source
    assert "duration-chip" in source
    assert "timeline-duration" in source
    assert "trace-duration" in source
    assert "duration_ms" in source


def test_frontend_shows_breathing_indicator_for_current_executing_node() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    node_status_body = source.split("function nodeStatus(nodeId) {", 1)[1].split("\n}", 1)[0]
    timeline_executing_rule = source.split(".timeline-node.status-executing {", 1)[1].split("}", 1)[
        0
    ]
    timeline_dot_pulse_rule = source.split(
        ".timeline-node.status-executing .timeline-dot::after {", 1
    )[1].split("}", 1)[0]
    workflow_executing_rule = source.split(".workflow-node.status-executing {", 1)[1].split("}", 1)[
        0
    ]

    assert "const isWorkflowExecuting = computed(() =>" in source
    assert "const currentExecutingNodeId = computed(() =>" in source
    assert "orderedFlowNodes.value.find((node) =>" in source
    assert "currentExecutingNodeId.value || waitingNodeId.value || selectedNodeId.value" in source
    assert 'executing: "运行中"' in source
    assert 'if (currentExecutingNodeId.value === nodeId) return "executing";' in node_status_body
    assert "animation: timelineBreathing" in timeline_executing_rule
    assert "box-shadow:" in timeline_executing_rule
    assert "animation: nodePulse" in timeline_dot_pulse_rule
    assert "animation: nodeBreathing" in workflow_executing_rule
    assert "@keyframes timelineBreathing" in source
    assert "@keyframes nodePulse" in source
    assert "@keyframes nodeBreathing" in source
    assert "@media (prefers-reduced-motion: reduce)" in source


def test_frontend_workflow_requests_use_shared_auth_http_layer() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "requestJson as requestWorkflowJson" in source
    assert 'from "../services/http"' in source
    assert "function requestJson(path, options = {})" not in source
    assert "await fetch(`${apiBase()}${path}`" not in source
    assert (
        "requestWorkflowJson(`/api/workflows/${workflowId}/template`, { target: workflowTarget() })"
        in source
    )
    assert (
        "requestWorkflowJson(`/api/workflows/${workflowId}/threads/${threadId.value}/trace`, { target: workflowTarget() })"
        in source
    )


def test_frontend_workflow_run_and_resume_use_shared_websocket_stream() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "openJsonStream" in source
    assert "fallbackWorkflowRequest(path, payload)" in source
    assert "fallbackJson" in source
    assert 'type: "run"' in source
    assert 'type: "resume"' in source
    assert "applyWorkflowTrace(message.trace)" in source
    assert "applyWorkflowResult(message.result)" in source
    assert (
        "requestWorkflowJson(`/api/workflows/${workflowId}/threads/${threadId.value}/resume`"
        in source
    )


def test_frontend_workflow_stream_surfaces_node_repair_status() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    node_status_body = source.split("function nodeStatus(nodeId) {", 1)[1].split("\n}", 1)[0]
    timeline_repairing_rule = source.split(".timeline-node.status-repairing {", 1)[1].split("}", 1)[
        0
    ]
    workflow_repairing_rule = source.split(".workflow-node.status-repairing {", 1)[1].split("}", 1)[
        0
    ]

    assert "const liveNodeStatuses = ref({});" in source
    assert 'if (message.type === "node_status") {' in source
    assert "applyWorkflowNodeStatus(message)" in source
    assert 'repairing: "自修复中"' in source
    assert "const liveStatus = liveNodeStatuses.value[nodeId];" in node_status_body
    assert "if (liveStatus) return liveStatus;" in node_status_body
    assert "animation: timelineBreathing" in timeline_repairing_rule
    assert "animation: nodeBreathing" in workflow_repairing_rule


def test_frontend_workflow_websocket_authorization_uses_bearer_token() -> None:
    source = Path("desktop/frontend/src/services/transport.js").read_text(encoding="utf-8")

    assert 'let accessToken = "";' in source
    assert "const token = accessToken;" in source
    assert 'authorization: token ? `Bearer ${token}` : "",' in source
    assert "{ Authorization: `Bearer ${token}` }" in source


def test_frontend_done_node_surfaces_final_delivery() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "const finalDelivery = computed(() =>" in source
    assert "runResult.value?.output" in source
    assert 'focusNode.value?.type === "output" || focusNode.value?.id === "done"' in source
    assert 'v-if="isFinalNode && finalDelivery"' in source
    assert "finalDelivery.title" in source
    assert "finalDelivery.style" in source
    assert "finalDelivery.lyrics" in source
    assert "Style Prompt" in source
    assert "歌词" in source


def test_frontend_node_library_only_appears_on_flow_canvas() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "v-if=\"centerTab === 'canvas'\"" in source
    assert "canvas-library" in source
    assert "timeline-node" in source
    assert '<aside class="left-rail">' in source
    assert '<section class="library-section">' not in source


def test_frontend_secondary_details_open_in_right_drawer() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "drawerMode = ref(null)" in source
    assert "drawerModes" in source
    assert "drawer-mode-switch" in source
    assert "side-drawer" in source
    assert "drawer-slide" in source
    assert "openDrawer('config')" in source
    assert "openDrawer('io')" in source
    assert "openDrawer('run')" in source
    assert "openDrawer('trace')" in source
    assert "openDrawer('result')" in source
    assert '@click="openDrawer(item.id)"' in source
    assert '<aside class="inspector">' not in source
    assert '<section class="run-dock">' not in source


def test_frontend_drawer_uses_compact_inspector_layout() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "drawer-titleline" in source
    assert "drawer-segmented" in source
    assert "drawer-content" in source
    assert "drawer-action-bar" in source
    assert "drawer-field" in source
    assert "drawer-primary-action" in source
    assert ".drawer-segmented button" in source
    assert ".drawer-action-bar" in source
    assert ".drawer-field input" in source
    assert ".drawer-field textarea" in source
    assert "secondary-run" not in source
    assert "inspector-actions" not in source
