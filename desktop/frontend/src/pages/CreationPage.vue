<script setup>
import { computed, onMounted, ref, watch } from "vue";
import {
  Activity,
  Braces,
  CheckCircle2,
  Circle,
  Clock3,
  GitBranch,
  Hand,
  ListPlus,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings2,
  SquarePen,
  Trash2,
  Workflow,
} from "@lucide/vue";
import { MarkerType, VueFlow } from "@vue-flow/core";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import { apiBase as resolveApiBase, requestJson as requestWorkflowJson } from "../services/http";
import { saveSong } from "../services/songs";

const workflowId = "pro_creation_hitl_v1";
const target = ref(localStorage.getItem("yts-target") || "local");
const bases = { local: "http://127.0.0.1:8765", cloud: "http://127.0.0.1:8000" };
const template = ref(null);
const draftTemplate = ref(null);
const threadId = ref(`workflow-${Date.now()}`);
const prompt = ref("下雨的午后，大雨倾盆，思念远方的故人");
const selectedNodeId = ref("validate_request");
const nodeConfigText = ref("{}");
const newNodeType = ref("hitl_approval");
const centerTab = ref("workspace");
const runResult = ref(null);
const trace = ref(null);
const result = ref(null);
const status = ref("idle");
const error = ref("");
const saveMessage = ref("");
const drawerMode = ref(null);
const drawerModes = [
  { id: "config", label: "配置", icon: Settings2 },
  { id: "io", label: "输入输出", icon: GitBranch },
  { id: "run", label: "运行", icon: Play },
  { id: "trace", label: "轨迹", icon: Clock3 },
  { id: "result", label: "结果", icon: Braces },
];

const nodeTypeMeta = {
  pro_stage: { label: "Pro 节点", icon: Workflow, tone: "blue" },
  hitl_approval: { label: "人工确认", icon: Hand, tone: "amber" },
  hitl_review: { label: "人工评审", icon: SquarePen, tone: "violet" },
  hitl_choose: { label: "人工选择", icon: GitBranch, tone: "green" },
  output: { label: "输出节点", icon: CheckCircle2, tone: "slate" },
};

const libraryNodes = [
  { type: "pro_stage", title: "Pro 节点", text: "规划、生成、评审或格式化" },
  { type: "hitl_approval", title: "人工确认", text: "暂停流程，等待确认或编辑" },
  { type: "hitl_review", title: "人工评审", text: "检查结果，接受或修改" },
  { type: "hitl_choose", title: "人工选择", text: "从结构化候选中选择" },
];

const flowStageDefinitions = [
  { id: "request", label: "01 输入校验", nodeIds: ["validate_request", "parse_intent"] },
  { id: "brief", label: "02 歌曲简报", nodeIds: ["build_song_brief", "brief_approval"] },
  { id: "style", label: "03 风格与 Hook", nodeIds: ["plan_music_style", "hook_lab"] },
  { id: "structure", label: "04 结构设计", nodeIds: ["draft_structure_blueprints", "critique_structure"] },
  {
    id: "lyrics",
    label: "05 歌词成稿",
    nodeIds: [
      "plan_style_prompt",
      "generate_lyrics",
      "review_quality",
      "repair_lyrics",
      "normalize_suno_format",
      "refine_title",
    ],
  },
  { id: "delivery", label: "06 交付评审", nodeIds: ["build_response", "final_review", "done"] },
];

const statusLabels = {
  idle: "空闲",
  draft: "草稿",
  waiting: "等待人工",
  completed: "已完成",
  running: "运行中",
  trace: "刷新轨迹",
  "loading-template": "加载模板",
  "resume-approve": "确认中",
  "resume-accept": "提交中",
  "resume-edit": "应用修改",
  "resume-reject": "拒绝中",
  "resume-rerun": "重跑中",
  "resume-choose": "选择中",
};

const actionLabels = {
  approve: "确认",
  edit: "编辑后继续",
  reject: "拒绝",
  accept: "接受",
  rerun: "重新运行",
  choose: "选择",
};

const traceStatusLabels = {
  completed: "已完成",
  waiting: "等待中",
  idle: "未运行",
  pending: "待执行",
};

const traceTypeLabels = {
  pro_stage: "Pro 节点",
  hitl_approval: "人工确认",
  hitl_review: "人工评审",
  hitl_choose: "人工选择",
  output: "输出节点",
};

const nodeTypeDescriptions = {
  pro_stage: "执行 Pro 歌词链路中的一个自动节点，产物会进入后续节点。",
  hitl_approval: "暂停流程，等待人工确认或编辑后继续。",
  hitl_review: "检查生成结果，接受、编辑或重新运行。",
  hitl_choose: "从结构化候选中选择一个分支。",
  output: "汇总最终输出。",
};

const selectedNode = computed(() => {
  return draftTemplate.value?.nodes.find((node) => node.id === selectedNodeId.value) ?? null;
});

const flowGroups = computed(() => {
  const nodes = draftTemplate.value?.nodes ?? [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  return flowStageDefinitions
    .map((group) => ({
      ...group,
      nodes: group.nodeIds.map((nodeId) => byId.get(nodeId)).filter(Boolean),
    }))
    .filter((group) => group.nodes.length);
});

const traceNodes = computed(() => trace.value?.nodes ?? runResult.value?.trace?.nodes ?? []);
const completedIds = computed(() => {
  return new Set(traceNodes.value.filter((node) => node.status === "completed").map((node) => node.node_id));
});
const waitingNodeId = computed(() => runResult.value?.waiting?.node_id ?? "");

const graphNodes = computed(() => {
  if (!draftTemplate.value) return [];
  return draftTemplate.value.nodes.map((node, index) => ({
    id: node.id,
    label: node.label,
    position: node.position ?? autoPosition(index),
    data: {
      nodeType: node.type,
      status: nodeStatus(node.id),
      meta: nodeTypeMeta[node.type] ?? nodeTypeMeta.output,
    },
    class: [
      "workflow-node",
      `tone-${nodeTone(node.type)}`,
      `status-${nodeStatus(node.id)}`,
      selectedNodeId.value === node.id ? "is-selected" : "",
    ].filter(Boolean).join(" "),
  }));
});

const graphEdges = computed(() => {
  if (!draftTemplate.value) return [];
  return draftTemplate.value.edges.map((edge) => ({
    id: `${edge.source}->${edge.target}`,
    source: edge.source,
    target: edge.target,
    label: edge.condition ?? "",
    markerEnd: MarkerType.ArrowClosed,
    animated: runResult.value?.status === "waiting",
    class: "workflow-edge",
  }));
});

const proStageCount = computed(() => {
  return draftTemplate.value?.nodes.filter((node) => node.type === "pro_stage").length ?? 0;
});

const hitlCount = computed(() => {
  return draftTemplate.value?.nodes.filter((node) => node.type.startsWith("hitl_")).length ?? 0;
});

const edgeCount = computed(() => draftTemplate.value?.edges.length ?? 0);
const selectedIncoming = computed(() => {
  return draftTemplate.value?.edges.filter((edge) => edge.target === selectedNodeId.value) ?? [];
});
const selectedOutgoing = computed(() => {
  return draftTemplate.value?.edges.filter((edge) => edge.source === selectedNodeId.value) ?? [];
});

const selectedNodeMeta = computed(() => {
  return nodeTypeMeta[selectedNode.value?.type] ?? nodeTypeMeta.output;
});

const focusNodeId = computed(() => waitingNodeId.value || selectedNodeId.value);
const focusNode = computed(() => {
  return draftTemplate.value?.nodes.find((node) => node.id === focusNodeId.value) ?? selectedNode.value;
});
const focusNodeMeta = computed(() => nodeTypeMeta[focusNode.value?.type] ?? nodeTypeMeta.output);
const focusNodeStatus = computed(() => nodeStatus(focusNode.value?.id ?? ""));
const focusTraceEntry = computed(() => {
  return [...traceNodes.value].reverse().find((node) => node.node_id === focusNode.value?.id) ?? null;
});
const focusTraceIds = computed(() => {
  const rootId = trace.value?.run_id ?? runResult.value?.trace?.run_id ?? runResult.value?.run_id ?? "";
  const spanId = focusTraceEntry.value?.span_id ?? "";
  return { rootId, spanId };
});
const focusDurationLabel = computed(() => formatDuration(focusTraceEntry.value?.duration_ms));
const completedCount = computed(() => completedIds.value.size);
const stageProgressText = computed(() => `${completedCount.value}/${draftTemplate.value?.nodes.length ?? 0}`);
const hasRunStarted = computed(() => Boolean(runResult.value || traceNodes.value.length));
const focusArtifact = computed(() => focusTraceEntry.value?.artifact_preview ?? {});
const artifactRows = computed(() => {
  return Object.entries(focusArtifact.value)
    .filter(([, value]) => hasArtifactValue(value))
    .map(([key, value]) => ({ key, label: artifactLabel(key), value: formatArtifactValue(value) }));
});
const nodeArtifactTitle = computed(() => (isFinalNode.value ? "最终交付" : "节点产物"));
const llmCall = computed(() => focusTraceEntry.value?.llm_call ?? null);
const llmInputJson = computed(() => {
  const messages = llmCall.value?.input_messages;
  if (!Array.isArray(messages) || !messages.length) return "";
  return formatJsonPreview(messages, "LLM 输入");
});
const llmOutputJson = computed(() => {
  if (!llmCall.value) return "";
  const parsed = llmCall.value.parsed_json;
  if (parsed && typeof parsed === "object") {
    return formatJsonPreview(parsed, "LLM 输出");
  }
  return formatJsonPreview(llmCall.value.response_text, "LLM 输出");
});
const llmInputPreview = computed(() => llmInputJson.value.text);
const llmOutputPreview = computed(() => llmOutputJson.value.text);
const finalDelivery = computed(() => {
  const output = result.value ?? runResult.value?.output ?? {};
  if (!output || typeof output !== "object") return null;
  const title = strValue(output.title);
  const style = strValue(output.style);
  const lyrics = strValue(output.lyrics);
  if (!title && !style && !lyrics) return null;
  return {
    title: title || "未命名",
    style,
    lyrics,
  };
});
const isFinalNode = computed(() => focusNode.value?.type === "output" || focusNode.value?.id === "done");
const workspaceSummary = computed(() => {
  if (runResult.value?.waiting) return runResult.value.waiting.prompt;
  if (isFinalNode.value && finalDelivery.value) return `已生成结果：${finalDelivery.value.title}`;
  if (focusTraceEntry.value?.summary) return focusTraceEntry.value.summary;
  if (result.value) return `已生成结果：${result.value.title ?? "未命名"}`;
  if (hasRunStarted.value) return "选择左侧节点查看该节点产物摘要、运行状态和最近 trace 事件。";
  return "尚未运行。";
});

const runStatusLabel = computed(() => {
  if (status.value !== "idle") return status.value;
  if (runResult.value?.status === "completed") return "completed";
  if (runResult.value?.waiting) return "waiting";
  return "draft";
});

const runStatusText = computed(() => statusLabels[runStatusLabel.value] ?? runStatusLabel.value);
const drawerTitle = computed(() => {
  const titles = {
    config: "节点配置",
    io: "输入输出",
    run: "运行输入",
    trace: "完整轨迹",
    result: "运行结果",
  };
  return titles[drawerMode.value] ?? "";
});

function apiBase() {
  return resolveApiBase(target.value);
}

async function withBusy(nextStatus, fn) {
  status.value = nextStatus;
  error.value = "";
  if (nextStatus !== "saving-asset") {
    saveMessage.value = "";
  }
  try {
    return await fn();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    return null;
  } finally {
    status.value = "idle";
  }
}

async function loadTemplate() {
  await withBusy("loading-template", async () => {
    template.value = await requestWorkflowJson(`/api/workflows/${workflowId}/template`);
    draftTemplate.value = cloneTemplateWithPositions(template.value);
    const current = draftTemplate.value.nodes.find((node) => node.id === selectedNodeId.value);
    selectedNodeId.value = current?.id ?? draftTemplate.value.start_node_id;
    resetSelectedNodeConfig();
  });
}

function parseNodeConfig() {
  const parsed = JSON.parse(nodeConfigText.value);
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("节点配置必须是 JSON 对象");
  }
  return parsed;
}

function formatJsonPreview(value, label) {
  if (value === undefined || value === null || value === "") {
    return { text: "", ok: false, error: "" };
  }
  try {
    const parsed = typeof value === "string" ? JSON.parse(value) : value;
    return { text: JSON.stringify(parsed, null, 2), ok: true, error: "" };
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    return {
      text: `${label}不是合法 JSON，无法格式化。\n${reason}`,
      ok: false,
      error: reason,
    };
  }
}

function resetSelectedNodeConfig() {
  nodeConfigText.value = JSON.stringify(selectedNode.value?.config ?? {}, null, 2);
}

function buildNodeConfigPayload() {
  if (!selectedNodeId.value) return {};
  return { [selectedNodeId.value]: parseNodeConfig() };
}

function applySelectedNodeConfig() {
  const node = selectedNode.value;
  if (!node) return;
  try {
    node.config = parseNodeConfig();
    error.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function addDraftNode(type = newNodeType.value) {
  if (!draftTemplate.value) return;
  const nodeId = `${type}_${Date.now()}`;
  const index = draftTemplate.value.nodes.length;
  const node = {
    id: nodeId,
    type,
    label: nodeTypeMeta[type]?.label ?? type,
    config: defaultConfigForNodeType(type),
    position: autoPosition(index),
  };
  draftTemplate.value.nodes.push(node);
  selectNode(nodeId);
}

function deleteSelectedDraftNode() {
  if (!draftTemplate.value || !selectedNode.value) return;
  if (selectedNode.value.type === "pro_stage") {
    error.value = "当前模板必须保留 Pro 节点";
    return;
  }
  draftTemplate.value.nodes = draftTemplate.value.nodes.filter((node) => node.id !== selectedNodeId.value);
  draftTemplate.value.edges = draftTemplate.value.edges.filter(
    (edge) => edge.source !== selectedNodeId.value && edge.target !== selectedNodeId.value,
  );
  selectedNodeId.value = draftTemplate.value.start_node_id;
  resetSelectedNodeConfig();
}

function cloneTemplateWithPositions(source) {
  return {
    ...source,
    nodes: source.nodes.map((node, index) => ({
      ...node,
      config: { ...(node.config ?? {}) },
      position: autoPosition(index),
    })),
    edges: source.edges.map((edge) => ({ ...edge })),
  };
}

function autoPosition(index) {
  const column = index % 5;
  const row = Math.floor(index / 5);
  return { x: 64 + column * 230, y: 74 + row * 150 };
}

function defaultConfigForNodeType(type) {
  if (type === "hitl_approval") {
    return { actions: ["approve", "edit", "reject"], editable_fields: ["user_prompt"] };
  }
  if (type === "hitl_review") {
    return { actions: ["accept", "edit", "rerun"], editable_fields: ["title", "style", "lyrics"] };
  }
  if (type === "hitl_choose") {
    return { actions: ["choose"], editable_fields: [], choices: [] };
  }
  if (type === "pro_stage") {
    return { stage: "custom_stage" };
  }
  return {};
}

async function runThread() {
  await withBusy("running", async () => {
    const body = {
      thread_id: threadId.value,
      user_prompt: prompt.value,
      node_config: buildNodeConfigPayload(),
    };
    runResult.value = await requestWorkflowJson(`/api/workflows/${workflowId}/threads`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    trace.value = runResult.value.trace;
    result.value = runResult.value.output;
  });
}

async function resumeThread(action) {
  const waiting = runResult.value?.waiting;
  if (!waiting) {
    error.value = "当前没有等待恢复的节点";
    return;
  }
  await withBusy(`resume-${action}`, async () => {
    runResult.value = await requestWorkflowJson(`/api/workflows/${workflowId}/threads/${threadId.value}/resume`, {
      method: "POST",
      body: JSON.stringify({
        node_id: waiting.node_id,
        action,
        patch: action === "edit" ? parseNodeConfig() : {},
      }),
    });
    trace.value = runResult.value.trace;
    result.value = runResult.value.output;
  });
}

async function refreshTrace() {
  await withBusy("trace", async () => {
    trace.value = await requestWorkflowJson(`/api/workflows/${workflowId}/threads/${threadId.value}/trace`);
  });
}

async function saveFinalDeliveryToAssets() {
  if (!finalDelivery.value) {
    error.value = "当前没有可保存的最终结果";
    return;
  }
  saveMessage.value = "";
  await withBusy("saving-asset", async () => {
    await saveSong({
      name: finalDelivery.value.title,
      prompt: prompt.value,
      style_prompt: finalDelivery.value.style,
      lyric_prompt: finalDelivery.value.lyrics,
      llm: "yts_pro_workflow",
    });
    saveMessage.value = "已保存到资产";
  });
}

function selectNode(nodeId) {
  selectedNodeId.value = nodeId;
  resetSelectedNodeConfig();
  centerTab.value = "workspace";
}

function openDrawer(mode) {
  drawerMode.value = mode;
}

function closeDrawer() {
  drawerMode.value = null;
}

function onNodeClick(event) {
  selectNode(event.node.id);
}

function nodeStatus(nodeId) {
  if (waitingNodeId.value === nodeId) return "waiting";
  if (completedIds.value.has(nodeId)) return "completed";
  return "idle";
}

function nodeTone(type) {
  return (nodeTypeMeta[type] ?? nodeTypeMeta.output).tone;
}

function nodeIcon(type) {
  return (nodeTypeMeta[type] ?? nodeTypeMeta.output).icon;
}

function nodeLabel(nodeId) {
  return draftTemplate.value?.nodes.find((node) => node.id === nodeId)?.label ?? nodeId;
}

function nodeTraceEntry(nodeId) {
  return [...traceNodes.value].reverse().find((node) => node.node_id === nodeId) ?? null;
}

function actionLabel(action) {
  return actionLabels[action] ?? action;
}

function traceStatusLabel(traceStatus) {
  return traceStatusLabels[traceStatus] ?? traceStatus;
}

function traceTypeLabel(traceType) {
  return traceTypeLabels[traceType] ?? traceType;
}

function formatDuration(durationMs) {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs)) return "--";
  if (durationMs < 1000) return `${Math.max(0, Math.round(durationMs))}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}

function artifactLabel(key) {
  const labels = {
    bpm_range: "BPM",
    blueprint_count: "蓝图数",
    blueprints: "结构候选",
    candidates: "候选",
    core_story: "核心故事",
    critic_notes: "评审意见",
    decision: "决策",
    emotion_arc: "情绪弧线",
    final_title: "最终标题",
    hook: "Hook",
    hook_strategy: "Hook 策略",
    instrumentation: "配器",
    lyric_excerpt: "歌词片段",
    lyrics_excerpt: "歌词片段",
    main_issues: "主要问题",
    negative_tags: "负面标签",
    negative_terms: "负面词",
    original_title: "原标题",
    overall_score: "总分",
    repair_attempted: "尝试修复",
    repair_succeeded: "修复成功",
    scene_cues: "场景线索",
    selected_blueprint_id: "选中蓝图",
    selected_hook: "选中 Hook",
    selected_label: "选中曲风",
    selected_style_id: "曲风 ID",
    selected_template_id: "模板 ID",
    selection_reason: "选择理由",
    style: "Style",
    style_components: "风格组件",
    style_family: "风格家族",
    style_prompt: "Style Prompt",
    structure: "结构",
    suggestions: "建议",
    target_form: "目标歌型",
    title: "标题",
    user_prompt: "需求",
    vocal_profile: "人声",
  };
  return labels[key] ?? key;
}

function formatArtifactValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => formatArtifactItem(item)).join(" / ");
  }
  if (value && typeof value === "object") {
    return Object.entries(value)
      .filter(([, item]) => hasArtifactValue(item))
      .map(([key, item]) => `${artifactLabel(key)}: ${formatArtifactItem(item)}`)
      .join(" / ");
  }
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function strValue(value) {
  return typeof value === "string" ? value.trim() : "";
}

function formatArtifactItem(item) {
  if (Array.isArray(item)) return item.map((nested) => formatArtifactItem(nested)).join(", ");
  if (item && typeof item === "object") {
    return Object.entries(item)
      .filter(([, value]) => hasArtifactValue(value))
      .map(([key, value]) => `${artifactLabel(key)}=${formatArtifactItem(value)}`)
      .join(", ");
  }
  if (typeof item === "boolean") return item ? "是" : "否";
  return String(item);
}

function hasArtifactValue(value) {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return value !== undefined && value !== null && String(value).trim() !== "";
}

watch(target, (nextTarget) => {
  localStorage.setItem("yts-target", nextTarget);
});

onMounted(loadTemplate);
</script>

<template>
  <main class="app-shell">
    <aside class="left-rail">
      <div class="brand-block">
        <div class="brand-mark"><Workflow :size="18" /></div>
        <div>
          <h1>深海工作室</h1>
          <p>制作流程</p>
        </div>
      </div>

      <section class="flow-nav-section compact-list">
        <div class="section-label">流程节点</div>
        <div v-for="group in flowGroups" :key="group.id" class="flow-stage-group">
          <div class="flow-stage-label">{{ group.label }}</div>
          <button
            v-for="node in group.nodes"
            :key="node.id"
            :class="['timeline-node', selectedNodeId === node.id ? 'active' : '', `status-${nodeStatus(node.id)}`]"
            type="button"
            @click="selectNode(node.id)"
          >
            <span class="timeline-track">
              <span :class="['timeline-dot', `tone-${nodeTone(node.type)}`]"></span>
            </span>
            <span class="timeline-copy">
              <strong>{{ node.label }}</strong>
              <small>{{ node.id }}</small>
            </span>
            <span class="timeline-meta">
              <span class="timeline-status">{{ traceStatusLabel(nodeStatus(node.id)) }}</span>
              <span class="timeline-duration">{{ formatDuration(nodeTraceEntry(node.id)?.duration_ms) }}</span>
            </span>
          </button>
        </div>
      </section>
    </aside>

    <section class="main-stage">
      <header class="topbar">
        <div class="title-stack">
          <div class="breadcrumb">工作流 / {{ workflowId }}</div>
          <div class="title-row">
            <h2>Pro 歌词创作流</h2>
            <span :class="['run-pill', runStatusLabel]">
              <Activity :size="14" />
              {{ runStatusText }}
            </span>
          </div>
        </div>

        <div class="top-actions">
          <div class="target-menu compact-target">
            <select v-model="target" aria-label="API 环境">
              <option value="local">本地</option>
              <option value="cloud">云端</option>
            </select>
            <span>{{ bases[target] }}</span>
          </div>
          <button class="icon-button" type="button" title="重新加载模板" @click="loadTemplate">
            <RefreshCw :size="17" />
          </button>
          <button class="icon-button" type="button" title="运行输入" @click="openDrawer('run')">
            <SquarePen :size="17" />
          </button>
          <button class="icon-button" type="button" title="节点配置" @click="openDrawer('config')">
            <Settings2 :size="17" />
          </button>
          <button class="primary-button" type="button" :disabled="status !== 'idle'" @click="runThread">
            <Play :size="16" />
            运行
          </button>
        </div>
      </header>

      <div class="center-tabs">
        <button :class="{ active: centerTab === 'workspace' }" type="button" @click="centerTab = 'workspace'">
          <Activity :size="15" />
          工作台
        </button>
        <button :class="{ active: centerTab === 'canvas' }" type="button" @click="centerTab = 'canvas'">
          <Workflow :size="15" />
          流程图
        </button>
      </div>

      <section v-if="centerTab === 'workspace'" class="workspace-card">
        <div class="workspace-header compact-focus-bar">
          <div class="workspace-title">
            <span :class="['workspace-icon', `tone-${nodeTone(focusNode?.type)}`]">
              <component :is="focusNodeMeta.icon" :size="17" />
            </span>
            <div>
              <div class="focus-heading">
                <span class="eyebrow">当前工作节点</span>
                <h3>{{ focusNode?.label ?? "未选择节点" }}</h3>
              </div>
              <p>{{ focusNode?.id ?? "请选择一个节点" }} · {{ focusNodeMeta.label }} · {{ workspaceSummary }}</p>
            </div>
          </div>
          <div class="trace-id-strip">
            <span><strong>root id</strong>{{ focusTraceIds.rootId || "未生成" }}</span>
            <span><strong>span id</strong>{{ focusTraceIds.spanId || "未生成" }}</span>
            <span class="duration-chip"><strong>duration</strong>{{ focusDurationLabel }}</span>
          </div>
          <div class="overview-chipline">
            <span class="progress-chip"><strong>{{ stageProgressText }}</strong> 完成</span>
            <span>{{ proStageCount }} Pro</span>
            <span>{{ hitlCount }} 人工</span>
            <span>{{ edgeCount }} 连线</span>
          </div>
          <div class="workspace-actions">
            <button type="button" title="输入输出" @click="openDrawer('io')">
              <GitBranch :size="15" />
            </button>
            <button type="button" title="节点配置" @click="openDrawer('config')">
              <Settings2 :size="15" />
            </button>
            <button type="button" title="完整轨迹" @click="openDrawer('trace')">
              <Clock3 :size="15" />
            </button>
            <button type="button" title="运行结果" @click="openDrawer('result')">
              <Braces :size="15" />
            </button>
            <span :class="['status-badge', focusNodeStatus]">{{ traceStatusLabel(focusNodeStatus) }}</span>
          </div>
        </div>

        <pre v-if="error" class="error-box compact-error">{{ error }}</pre>
        <div v-if="runResult?.waiting && focusNode?.id === runResult.waiting.node_id" class="workspace-gate compact-gate">
          <div>
            <strong>{{ runResult.waiting.kind === "approval" ? "等待确认" : "等待处理" }}</strong>
            <span>{{ runResult.waiting.prompt }}</span>
          </div>
          <div class="gate-actions">
            <button
              v-for="action in runResult.waiting.actions"
              :key="action"
              type="button"
              :disabled="status !== 'idle'"
              @click="resumeThread(action)"
            >
              {{ actionLabel(action) }}
            </button>
          </div>
        </div>
        <div v-else class="workspace-note compact-note">
          {{ nodeTypeDescriptions[focusNode?.type] ?? "查看节点配置和运行状态。" }}
        </div>

        <section v-if="isFinalNode && finalDelivery" class="workspace-panel final-delivery">
          <div class="section-label">{{ nodeArtifactTitle }}</div>
            <header class="delivery-head">
              <span>歌名</span>
              <h4>{{ finalDelivery.title }}</h4>
              <button type="button" :disabled="status !== 'idle'" @click="saveFinalDeliveryToAssets">
                <Save :size="15" />
                保存到资产
              </button>
            </header>
            <p v-if="saveMessage" class="save-message">{{ saveMessage }}</p>
            <div class="delivery-block">
              <span>Style Prompt</span>
              <p>{{ finalDelivery.style || "暂无 Style Prompt" }}</p>
            </div>
            <div class="delivery-block lyrics">
              <span>歌词</span>
              <pre>{{ finalDelivery.lyrics || "暂无歌词" }}</pre>
            </div>
        </section>

        <div v-else class="diagnostic-core">
          <section class="workspace-panel artifact-panel diagnostic-main">
            <div class="section-label">{{ nodeArtifactTitle }}</div>
            <div class="diagnostic-scroll">
              <dl v-if="artifactRows.length" class="artifact-list">
                <div v-for="row in artifactRows" :key="row.key" class="artifact-row">
                  <dt>{{ row.label }}</dt>
                  <dd>{{ row.value }}</dd>
                </div>
              </dl>
              <div v-else class="workspace-note">暂无节点产物。</div>
            </div>
          </section>

          <aside class="diagnostic-side">
            <section class="workspace-panel llm-panel">
              <div class="llm-title-row">
                <div class="section-label">LLM 输入</div>
                <span v-if="llmInputPreview" :class="['json-chip', llmInputJson.ok ? 'ok' : 'error']">
                  {{ llmInputJson.ok ? "已格式化 JSON" : "JSON 无效" }}
                </span>
              </div>
              <pre v-if="llmInputPreview" :class="['llm-code', llmInputJson.ok ? '' : 'invalid-json']">{{ llmInputPreview }}</pre>
              <div v-else class="workspace-note">暂无调用记录。</div>
            </section>
            <section class="workspace-panel llm-panel">
              <div class="llm-title-row">
                <div class="section-label">LLM 输出</div>
                <span v-if="llmOutputPreview" :class="['json-chip', llmOutputJson.ok ? 'ok' : 'error']">
                  {{ llmOutputJson.ok ? "已格式化 JSON" : "JSON 无效" }}
                </span>
              </div>
              <pre v-if="llmOutputPreview" :class="['llm-code', llmOutputJson.ok ? '' : 'invalid-json']">{{ llmOutputPreview }}</pre>
              <div v-else class="workspace-note">暂无调用记录。</div>
            </section>
          </aside>
        </div>
      </section>

      <section v-if="centerTab === 'canvas'" class="canvas-card">
        <div class="canvas-toolbar">
          <div class="toolbar-left">
            <Search :size="16" />
            <span>画布</span>
          </div>
          <div class="toolbar-right">
            <button type="button"><RotateCcw :size="15" /> 重置视图</button>
            <button type="button"><Save :size="15" /> 保存草稿</button>
          </div>
        </div>
        <div class="canvas-body">
          <aside class="canvas-library">
            <div class="section-label">节点库</div>
            <button
              v-for="item in libraryNodes"
              :key="item.type"
              class="library-item"
              type="button"
              @click="addDraftNode(item.type)"
            >
              <component :is="nodeIcon(item.type)" :size="16" />
              <span>
                <strong>{{ item.title }}</strong>
                <small>{{ item.text }}</small>
              </span>
              <ListPlus :size="15" />
            </button>
          </aside>
          <VueFlow
            class="flow-canvas"
            :nodes="graphNodes"
            :edges="graphEdges"
            :fit-view-on-init="true"
            :nodes-draggable="true"
            :nodes-connectable="false"
            :elements-selectable="true"
            @node-click="onNodeClick"
          >
            <template #node-default="{ data, label }">
              <div class="node-content">
                <div class="node-topline">
                  <span class="node-icon"><component :is="data.meta.icon" :size="15" /></span>
                  <span class="node-status" :data-status="data.status"></span>
                </div>
                <strong>{{ label }}</strong>
                <small>{{ data.meta.label }}</small>
              </div>
            </template>
          </VueFlow>
        </div>
      </section>
    </section>

    <Transition name="drawer-slide">
      <div v-if="drawerMode" class="drawer-backdrop" @click.self="closeDrawer">
        <aside class="side-drawer">
          <header class="drawer-head">
            <div class="drawer-titleline">
              <span class="eyebrow">{{ selectedNode?.label ?? "当前工作流" }}</span>
              <h3>{{ drawerTitle }}</h3>
            </div>
            <button class="icon-button" type="button" title="关闭" @click="closeDrawer">×</button>
          </header>
          <nav class="drawer-mode-switch drawer-segmented" aria-label="详情类型">
            <button
              v-for="item in drawerModes"
              :key="item.id"
              :class="{ active: drawerMode === item.id }"
              type="button"
              @click="openDrawer(item.id)"
            >
              <component :is="item.icon" :size="14" />
              {{ item.label }}
            </button>
          </nav>

          <div class="drawer-content">
            <section v-if="drawerMode === 'config'" class="drawer-panel">
              <label class="drawer-field">
                <span>节点 ID</span>
                <input :value="selectedNode?.id ?? ''" readonly />
              </label>
              <label class="drawer-field fill">
                <span>配置 JSON</span>
                <textarea v-model="nodeConfigText" spellcheck="false" />
              </label>
              <footer class="drawer-action-bar">
                <button type="button" @click="resetSelectedNodeConfig"><RotateCcw :size="15" /> 重置</button>
                <button type="button" @click="deleteSelectedDraftNode"><Trash2 :size="15" /> 删除</button>
                <button class="primary-button drawer-primary-action" type="button" @click="applySelectedNodeConfig">
                  <Save :size="15" />
                  应用
                </button>
              </footer>
            </section>

            <section v-else-if="drawerMode === 'io'" class="drawer-panel">
              <div class="io-block">
                <div class="section-label">输入</div>
                <div v-for="edge in selectedIncoming" :key="edge.source" class="edge-row">
                  <Circle :size="9" />
                  {{ nodeLabel(edge.source) }}
                </div>
                <div v-if="!selectedIncoming.length" class="empty-row">暂无输入连线</div>
              </div>
              <div class="io-block">
                <div class="section-label">输出</div>
                <div v-for="edge in selectedOutgoing" :key="edge.target" class="edge-row">
                  <Circle :size="9" />
                  {{ nodeLabel(edge.target) }}
                </div>
                <div v-if="!selectedOutgoing.length" class="empty-row">暂无输出连线</div>
              </div>
            </section>

            <section v-else-if="drawerMode === 'run'" class="drawer-panel">
              <label class="drawer-field">
                <span>线程 ID</span>
                <input v-model="threadId" />
              </label>
              <label class="drawer-field fill">
                <span>创作需求</span>
                <textarea v-model="prompt" class="prompt-box" />
              </label>
              <pre v-if="error" class="error-box">{{ error }}</pre>
              <footer class="drawer-action-bar">
                <button
                  class="primary-button drawer-primary-action"
                  type="button"
                  :disabled="status !== 'idle'"
                  @click="runThread"
                >
                  <Play :size="15" />
                  运行当前模板
                </button>
              </footer>
            </section>

            <section v-else-if="drawerMode === 'trace'" class="drawer-panel">
              <div class="drawer-toolbar">
                <button type="button" :disabled="status !== 'idle'" @click="refreshTrace">
                  <RefreshCw :size="15" />
                  刷新
                </button>
              </div>
              <ol class="trace-list drawer-list">
                <li v-for="node in traceNodes" :key="`${node.node_id}-${node.status}`">
                  <span :data-status="node.status"></span>
                  <strong>
                    {{ nodeLabel(node.node_id) }}
                    <small>{{ node.node_id }}</small>
                  </strong>
                  <em>{{ node.summary || traceTypeLabel(node.node_type) }}</em>
                  <small class="trace-duration">{{ formatDuration(node.duration_ms) }}</small>
                  <small>{{ traceStatusLabel(node.status) }}</small>
                </li>
              </ol>
            </section>

            <section v-else-if="drawerMode === 'result'" class="drawer-panel">
              <pre class="result-box">{{ result ? JSON.stringify(result, null, 2) : JSON.stringify(runResult?.waiting ?? {}, null, 2) }}</pre>
            </section>
          </div>
        </aside>
      </div>
    </Transition>
  </main>
</template>

<style>
:root {
  color: var(--color-text);
  background: var(--color-bg);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 1240px;
  background: var(--color-bg);
}

button,
input,
select,
textarea {
  font: inherit;
}

button {
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-panel);
  color: var(--color-text);
  cursor: pointer;
  display: inline-flex;
  gap: 7px;
  justify-content: center;
  min-height: 34px;
  padding: 0 11px;
}

button:disabled {
  color: var(--color-muted);
  cursor: not-allowed;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-panel);
  color: var(--color-text);
  padding: 9px 10px;
}

textarea {
  resize: vertical;
}

.app-shell {
  display: grid;
  grid-template-columns: 230px minmax(760px, 1fr);
  min-height: 100vh;
}

.left-rail {
  background: var(--color-panel);
  border-color: var(--color-border);
  border-style: solid;
  min-height: 100vh;
  padding: 14px;
}

.left-rail {
  border-width: 0 1px 0 0;
}

.brand-block,
.drawer-head {
  align-items: center;
  display: flex;
  gap: 11px;
}

.brand-mark,
.node-icon {
  align-items: center;
  border-radius: 9px;
  display: inline-flex;
  justify-content: center;
}

.brand-mark {
  background: var(--color-accent-soft);
  color: var(--color-accent);
  height: 34px;
  width: 34px;
}

.brand-block h1,
.title-row h2,
.drawer-head h3 {
  margin: 0;
}

.brand-block h1 {
  font-size: 16px;
}

.brand-block p,
.breadcrumb,
.section-label,
.library-item small,
.timeline-node,
.timeline-copy small,
.timeline-status,
.target-menu span,
.node-content small,
.edge-row,
.empty-row,
.eyebrow,
.workspace-title p,
.workspace-panel p,
.workspace-note,
.workspace-gate span,
.progress-strip span,
.status-grid span,
.trace-list em,
.trace-list small {
  color: var(--color-muted);
}

.brand-block p {
  font-size: 12px;
  margin: 2px 0 0;
}

.flow-nav-section {
  margin-top: 22px;
}

.section-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  margin-bottom: 9px;
}

.library-item,
.timeline-node {
  width: 100%;
}

.library-item {
  align-items: center;
  display: grid;
  gap: 10px;
  grid-template-columns: 20px 1fr 16px;
  height: auto;
  justify-content: start;
  margin-bottom: 8px;
  padding: 10px;
  text-align: left;
}

.library-item span {
  display: grid;
  gap: 2px;
}

.library-item strong {
  font-size: 13px;
}

.library-item small {
  font-size: 11px;
  line-height: 1.25;
}

.compact-list {
  max-height: calc(100vh - 104px);
  overflow: auto;
}

.flow-stage-group {
  border-left: 1px solid var(--color-border-soft);
  margin-left: 7px;
  padding: 0 0 9px 8px;
}

.flow-stage-label {
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
  margin: 3px 0 4px;
}

.timeline-node {
  background: transparent;
  border: 0;
  border-radius: 8px;
  display: grid;
  gap: 8px;
  grid-template-columns: 14px minmax(0, 1fr) auto;
  justify-content: stretch;
  margin-bottom: 3px;
  min-height: 42px;
  padding: 6px 7px;
  text-align: left;
}

.timeline-node.active {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.timeline-track {
  align-items: center;
  display: flex;
  height: 100%;
  justify-content: center;
  position: relative;
}

.timeline-track::before {
  background: var(--color-border-soft);
  content: "";
  height: 100%;
  left: 50%;
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  width: 1px;
}

.timeline-dot {
  border: 2px solid var(--color-panel);
  border-radius: 50%;
  height: 9px;
  position: relative;
  width: 9px;
  z-index: 1;
}

.timeline-copy {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.timeline-copy strong,
.timeline-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-copy strong {
  font-size: 13px;
}

.timeline-copy small,
.timeline-status,
.timeline-duration {
  font-size: 10px;
}

.timeline-meta {
  align-self: center;
  display: grid;
  gap: 3px;
  justify-items: end;
}

.timeline-status {
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  padding: 2px 6px;
}

.timeline-duration {
  color: var(--color-muted);
  line-height: 1;
}

.timeline-node.status-completed .timeline-status {
  background: var(--color-success-soft);
  border-color: var(--color-success);
  color: var(--color-success);
}

.timeline-node.status-waiting .timeline-status {
  background: var(--color-warning-soft);
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.main-stage {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  min-width: 0;
  padding: 14px;
}

.topbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.title-stack,
.title-row {
  min-width: 0;
}

.breadcrumb {
  font-size: 12px;
  margin-bottom: 5px;
}

.title-row {
  align-items: center;
  display: flex;
  gap: 10px;
}

.title-row h2 {
  font-size: 20px;
  white-space: nowrap;
}

.run-pill {
  align-items: center;
  border-radius: 999px;
  display: inline-flex;
  font-size: 12px;
  gap: 5px;
  padding: 5px 9px;
}

.run-pill.draft {
  background: var(--color-panel-strong);
}

.run-pill.waiting {
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.run-pill.completed {
  background: var(--color-success-soft);
  color: var(--color-success);
}

.top-actions {
  align-items: center;
  flex: 0 0 auto;
  display: flex;
  gap: 9px;
}

.target-menu {
  --target-font-size: 12px;
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  display: grid;
  gap: 8px;
  grid-template-columns: 78px 136px;
  min-height: 38px;
  padding: 0 8px;
}

.target-menu select {
  border: 0;
  padding: 0;
}

.target-menu span {
  font-size: var(--target-font-size);
}

.compact-target {
  border-radius: 8px;
  gap: 6px;
  grid-template-columns: 58px 124px;
  min-height: 32px;
  padding: 3px 7px;
}

.compact-target select {
  appearance: none;
  background-color: var(--color-panel);
  background-image: url("data:image/svg+xml,%3Csvg width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%23abc2d6' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-position: right 7px center;
  background-repeat: no-repeat;
  background-size: 14px 14px;
  border: 0;
  font-size: var(--target-font-size);
  line-height: 1;
  min-height: 24px;
  padding: 0 18px 0 7px;
}

.compact-target span {
  font-size: var(--target-font-size);
  line-height: 1;
}

.icon-button {
  width: 38px;
}

.primary-button {
  background: var(--color-accent-strong);
  border-color: var(--color-accent-strong);
  color: var(--color-heading);
}

.center-tabs {
  align-items: center;
  display: flex;
  gap: 8px;
  margin: 14px 0;
}

.center-tabs button {
  min-height: 32px;
}

.center-tabs button.active {
  background: var(--color-accent-soft);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.workspace-card,
.canvas-card {
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  min-width: 0;
  overflow: hidden;
}

.workspace-card {
  align-content: start;
  display: grid;
  gap: 10px;
  min-height: calc(100vh - 110px);
  padding: 12px;
}

.workspace-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.compact-focus-bar {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(240px, 1fr) minmax(180px, 0.82fr) minmax(220px, auto) auto;
  min-height: 64px;
  padding: 10px;
}

.workspace-title {
  align-items: center;
  display: flex;
  gap: 12px;
  min-width: 0;
}

.workspace-title > div {
  min-width: 0;
}

.focus-heading {
  align-items: baseline;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.workspace-title h3 {
  font-size: 17px;
  margin: 1px 0 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-title p,
.workspace-panel p {
  font-size: 12px;
  margin: 0;
}

.workspace-title p {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.eyebrow {
  font-size: 11px;
  font-weight: 700;
}

.workspace-icon {
  align-items: center;
  border-radius: 8px;
  display: inline-flex;
  flex: 0 0 auto;
  height: 36px;
  justify-content: center;
  width: 36px;
}

.workspace-icon.tone-blue,
.timeline-dot.tone-blue {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.workspace-icon.tone-amber,
.timeline-dot.tone-amber {
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.workspace-icon.tone-violet,
.timeline-dot.tone-violet {
  background: #2b1d4a;
  color: #a78bfa;
}

.workspace-icon.tone-green,
.timeline-dot.tone-green {
  background: var(--color-success-soft);
  color: var(--color-success);
}

.workspace-icon.tone-slate,
.timeline-dot.tone-slate {
  background: var(--color-panel-strong);
  color: var(--color-muted-strong);
}

.workspace-actions {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  gap: 7px;
}

.workspace-actions button {
  height: 32px;
  min-height: 32px;
  padding: 0;
  width: 32px;
}

.status-badge {
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  color: var(--color-muted-strong);
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
  padding: 5px 10px;
}

.trace-id-strip,
.overview-chipline {
  align-items: center;
  align-self: center;
  display: flex;
  gap: 7px;
  min-width: 0;
}

.trace-id-strip span,
.overview-chipline span {
  background: var(--color-panel);
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  color: var(--color-muted);
  font-size: 11px;
  line-height: 1;
  min-width: 0;
  padding: 6px 8px;
  white-space: nowrap;
}

.trace-id-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.overview-chipline {
  justify-content: flex-end;
}

.trace-id-strip span {
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}

.trace-id-strip strong {
  color: var(--color-text);
  font-weight: 800;
  margin-right: 5px;
}

.duration-chip {
  border-color: var(--color-border-soft);
}

.overview-chipline strong {
  color: var(--color-text);
  font-weight: 800;
}

.progress-chip {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.status-badge.completed {
  background: var(--color-success-soft);
  border-color: var(--color-success);
  color: var(--color-success);
}

.status-badge.waiting {
  background: var(--color-warning-soft);
  border-color: var(--color-warning);
  color: var(--color-warning);
}

.workspace-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1.35fr) minmax(250px, 0.65fr);
}

.workspace-grid.lower {
  grid-template-columns: minmax(0, 1fr) minmax(250px, 0.8fr);
}

.workspace-grid.lower.single {
  grid-template-columns: minmax(0, 1fr);
}

.workspace-panel {
  align-content: start;
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: grid;
  gap: 8px;
  grid-auto-rows: max-content;
  min-width: 0;
  padding: 10px;
}

.workspace-panel.primary {
  align-content: start;
}

.workspace-panel.primary p {
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.55;
}

.workspace-note {
  background: var(--color-panel);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.4;
  padding: 9px;
}

.compact-note {
  padding: 8px 10px;
}

.workspace-gate {
  align-items: center;
  background: var(--color-warning-soft);
  border: 1px solid var(--color-warning);
  border-radius: 8px;
  display: flex;
  gap: 14px;
  justify-content: space-between;
  padding: 10px;
}

.compact-gate {
  min-height: 46px;
  padding: 8px 10px;
}

.workspace-gate div:first-child {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.workspace-gate span {
  font-size: 12px;
  line-height: 1.45;
}

.progress-strip {
  align-items: end;
  border-bottom: 1px solid var(--color-border-soft);
  display: flex;
  gap: 9px;
  padding-bottom: 10px;
}

.progress-strip strong {
  font-size: 28px;
  line-height: 1;
}

.progress-strip span {
  font-size: 12px;
}

.status-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.status-grid div {
  background: var(--color-panel);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: grid;
  gap: 2px;
  padding: 9px;
}

.status-grid strong {
  font-size: 18px;
}

.status-grid span {
  font-size: 12px;
}

.artifact-panel {
  align-content: start;
}

.diagnostic-core {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  min-height: 0;
}

.diagnostic-main,
.diagnostic-side {
  min-height: calc(100vh - 248px);
}

.diagnostic-side {
  display: grid;
  gap: 10px;
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  min-width: 0;
}

.diagnostic-scroll,
.llm-code {
  min-height: 0;
  overflow: auto;
}

.llm-panel {
  align-content: stretch;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
}

.llm-panel .workspace-note {
  align-self: start;
}

.llm-title-row {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.llm-title-row .section-label {
  margin-bottom: 0;
}

.json-chip {
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  padding: 5px 7px;
}

.json-chip.ok {
  background: var(--color-accent-soft);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.json-chip.error {
  background: var(--color-danger-soft);
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.llm-code {
  background: var(--color-panel);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  color: var(--color-text);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  line-height: 1.45;
  margin: 0;
  padding: 10px;
  white-space: pre-wrap;
}

.llm-code.invalid-json {
  background: var(--color-danger-soft);
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.final-delivery {
  align-content: start;
  gap: 12px;
}

.delivery-head,
.delivery-block {
  background: var(--color-panel);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: grid;
  gap: 6px;
  padding: 12px;
}

.delivery-head span,
.delivery-block span {
  color: var(--color-muted-strong);
  font-size: 11px;
  font-weight: 700;
}

.delivery-head h4 {
  font-size: 22px;
  margin: 0;
}

.delivery-block p,
.delivery-block pre {
  color: var(--color-text);
  font-size: 13px;
  line-height: 1.55;
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.delivery-block.lyrics pre {
  max-height: 420px;
  overflow: auto;
}

.artifact-list {
  display: grid;
  gap: 8px;
  margin: 0;
}

.artifact-row {
  background: var(--color-panel);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: grid;
  gap: 4px;
  grid-template-columns: 104px minmax(0, 1fr);
  padding: 9px 10px;
}

.artifact-row dt {
  color: var(--color-muted-strong);
  font-size: 12px;
  font-weight: 700;
}

.artifact-row dd {
  color: var(--color-text);
  font-size: 12px;
  line-height: 1.45;
  margin: 0;
  overflow-wrap: anywhere;
}

.canvas-toolbar {
  align-items: center;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  height: 42px;
  justify-content: space-between;
  padding: 0 12px;
}

.toolbar-left,
.toolbar-right,
.drawer-toolbar,
.gate-actions {
  align-items: center;
  display: flex;
  gap: 8px;
}

.toolbar-left {
  color: var(--color-muted-strong);
  font-size: 13px;
  font-weight: 700;
}

.toolbar-right button,
.drawer-toolbar button {
  min-height: 30px;
}

.canvas-body {
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  min-height: 520px;
}

.canvas-library {
  border-right: 1px solid var(--color-border);
  background: var(--color-panel-strong);
  padding: 12px;
}

.flow-canvas {
  background-color: var(--color-panel-strong);
  background-image: radial-gradient(var(--color-border-soft) 1px, transparent 1px);
  background-size: 18px 18px;
  height: 100%;
  min-height: 520px;
}

.workflow-node {
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
  color: var(--color-text);
  width: 178px;
}

.workflow-node.is-selected {
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18), 0 10px 22px rgba(15, 23, 42, 0.12);
}

.workflow-node.tone-blue {
  border-top: 3px solid var(--color-accent);
}

.workflow-node.tone-amber {
  border-top: 3px solid var(--color-warning);
}

.workflow-node.tone-violet {
  border-top: 3px solid #7c3aed;
}

.workflow-node.tone-green {
  border-top: 3px solid #059669;
}

.workflow-node.status-completed {
  border-color: var(--color-success);
}

.workflow-node.status-waiting {
  border-color: #f2bd61;
}

.node-content {
  display: grid;
  gap: 5px;
  padding: 11px;
}

.node-topline {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.node-icon {
  background: var(--color-panel-soft);
  color: var(--color-muted-strong);
  height: 24px;
  width: 24px;
}

.node-content strong {
  font-size: 13px;
  line-height: 1.25;
}

.node-content small {
  font-size: 11px;
}

.node-status {
  border-radius: 50%;
  height: 8px;
  width: 8px;
  background: var(--color-muted);
}

.node-status[data-status="completed"],
.trace-list span[data-status="completed"] {
  background: var(--color-success);
}

.node-status[data-status="waiting"],
.trace-list span[data-status="waiting"] {
  background: var(--color-warning);
}

.trace-list {
  display: grid;
  gap: 4px;
  list-style: none;
  margin: 0;
  max-height: 128px;
  overflow: auto;
  padding: 0;
}

.trace-list li {
  align-items: center;
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: grid;
  gap: 8px;
  grid-template-columns: 9px minmax(150px, 0.65fr) minmax(220px, 1fr) 64px 76px;
  min-height: 42px;
  padding: 0 9px;
}

.trace-list span[data-status] {
  border-radius: 50%;
  height: 8px;
  width: 8px;
  background: var(--color-muted);
}

.trace-list strong,
.trace-list em,
.trace-list small {
  font-size: 12px;
  font-style: normal;
}

.trace-duration {
  color: var(--color-muted-strong);
  font-weight: 700;
}

.trace-list strong {
  display: grid;
  gap: 1px;
}

.trace-list em {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-list strong small {
  color: var(--color-muted);
  font-weight: 500;
}

.error-box,
.result-box {
  border-radius: 9px;
  margin: 0;
  overflow: auto;
  padding: 10px;
  white-space: pre-wrap;
}

.error-box {
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
  margin-bottom: 12px;
  max-height: 88px;
}

.compact-error {
  margin-bottom: 0;
}

.result-box {
  background: var(--color-sidebar);
  color: var(--color-text);
  max-height: 128px;
}

.io-block {
  display: grid;
  gap: 7px;
}

.edge-row,
.empty-row {
  align-items: center;
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: flex;
  font-size: 12px;
  gap: 8px;
  min-height: 32px;
  padding: 0 9px;
}

.drawer-backdrop {
  background: rgba(15, 23, 42, 0.2);
  display: flex;
  inset: 0;
  justify-content: flex-end;
  position: fixed;
  z-index: 50;
}

.side-drawer {
  background: var(--color-panel);
  border-left: 1px solid var(--color-border);
  box-shadow: -18px 0 40px rgba(15, 23, 42, 0.16);
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  height: 100vh;
  max-width: min(520px, 100vw);
  min-width: 460px;
  padding: 12px;
  width: 34vw;
}

.drawer-head {
  align-items: center;
  border-bottom: 1px solid var(--color-border-soft);
  justify-content: space-between;
  min-height: 48px;
  padding-bottom: 10px;
}

.drawer-titleline {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.drawer-head h3 {
  font-size: 16px;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-mode-switch {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  display: grid;
  gap: 3px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin-top: 10px;
  padding: 3px;
}

.drawer-segmented {
  min-height: 34px;
}

.drawer-segmented button {
  border: 0;
  border-radius: 6px;
  gap: 5px;
  min-height: 28px;
  min-width: 0;
  padding: 0 7px;
  white-space: nowrap;
}

.drawer-segmented button.active {
  background: var(--color-panel);
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.1);
  color: var(--color-accent);
}

.drawer-content {
  min-height: 0;
  overflow: hidden;
}

.drawer-panel {
  align-content: start;
  display: grid;
  gap: 10px;
  grid-auto-rows: max-content;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  padding-top: 10px;
}

.drawer-field {
  align-content: start;
  color: var(--color-muted-strong);
  display: grid;
  font-size: 12px;
  gap: 5px;
  min-height: 0;
}

.drawer-field > span {
  font-weight: 700;
}

.drawer-field input,
.drawer-field textarea {
  border-radius: 8px;
  font-size: 13px;
  padding: 8px 10px;
}

.drawer-field input {
  min-height: 34px;
}

.drawer-field textarea {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  min-height: 220px;
}

.drawer-panel .prompt-box {
  font-family: inherit;
  font-size: inherit;
  min-height: 140px;
}

.drawer-field.fill {
  align-content: stretch;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
}

.drawer-field.fill textarea {
  height: 100%;
  min-height: 180px;
}

.drawer-panel:has(.drawer-action-bar) {
  align-content: stretch;
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.drawer-action-bar {
  align-items: center;
  background: var(--color-panel);
  border-top: 1px solid var(--color-border-soft);
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: auto;
  padding-top: 10px;
}

.drawer-action-bar button {
  min-height: 32px;
}

.drawer-primary-action {
  min-width: 132px;
}

.drawer-toolbar {
  justify-content: flex-end;
}

.drawer-list {
  max-height: calc(100vh - 132px);
  overflow: auto;
}

.drawer-list li {
  grid-template-columns: 9px minmax(130px, 0.65fr) minmax(140px, 1fr) 58px 64px;
}

.drawer-panel .result-box {
  max-height: calc(100vh - 118px);
}

.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: opacity 0.18s ease;
}

.drawer-slide-enter-active .side-drawer,
.drawer-slide-leave-active .side-drawer {
  transition: transform 0.22s ease;
}

.drawer-slide-enter-from,
.drawer-slide-leave-to {
  opacity: 0;
}

.drawer-slide-enter-from .side-drawer,
.drawer-slide-leave-to .side-drawer {
  transform: translateX(100%);
}
</style>
