from __future__ import annotations

from pathlib import Path

WORKFLOW_SOURCE = Path("desktop/frontend/src/pages/CreationPage.vue")


def test_frontend_defaults_to_workspace_before_flow_canvas() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert 'centerTab = ref("workspace")' in source
    assert "工作台" in source
    assert 'v-if="centerTab === \'workspace\'"' in source
    assert 'v-if="centerTab === \'canvas\'"' in source


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
    assert "formatJsonPreview(llmCall.value.response_text, \"LLM 输出\")" in source


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


def test_frontend_flow_navigation_is_grouped_by_workflow_stage() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "const flowGroups = computed(() =>" in source
    assert "flow-stage-group" in source
    assert "flow-stage-label" in source
    assert "group.nodes" in source
    assert "brief_approval" in source
    assert "final_review" in source


def test_frontend_target_selector_uses_toolbar_density() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "target-menu compact-target" in source
    assert ".compact-target select" in source
    assert ".compact-target span" in source


def test_frontend_target_selector_aligns_select_text_and_arrow() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "appearance: none;" in source
    assert "background-position: right 7px center;" in source
    assert "font-size: var(--target-font-size);" in source
    assert "--target-font-size: 12px;" in source
    assert "padding: 3px 7px;" in source


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


def test_frontend_workflow_requests_use_shared_auth_http_layer() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert 'requestJson as requestWorkflowJson' in source
    assert 'from "../services/http"' in source
    assert "function requestJson(path, options = {})" not in source
    assert "await fetch(`${apiBase()}${path}`" not in source


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

    assert 'v-if="centerTab === \'canvas\'"' in source
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
    assert "@click=\"openDrawer(item.id)\"" in source
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
