<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import {
  Activity,
  ArrowUp,
  Braces,
  CheckCircle2,
  Circle,
  Clock3,
  Copy,
  FileText,
  GitBranch,
  Hand,
  History,
  ListPlus,
  MessageSquare,
  Plus,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings2,
  Sparkles,
  SquarePen,
  Trash2,
  Workflow,
} from "@lucide/vue";
import { MarkerType, VueFlow } from "@vue-flow/core";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import {
  API_TARGET_CHANGED_EVENT,
  requestJson as requestWorkflowJson,
  selectedApiTarget,
} from "../services/http";
import { saveSong } from "../services/songs";
import { openJsonStream } from "../services/transport";
import { getWorkflowRunResult, listWorkflowHistory } from "../services/workflows";
import { useEnvironmentStore } from "../stores/environment";

const workflowId = "pro_creation_hitl_v1";
const environment = useEnvironmentStore();
const template = ref(null);
const draftTemplate = ref(null);
const threadId = ref(`workflow-${Date.now()}`);
const prompt = ref("");
const selectedNodeId = ref("validate_request");
const userSelectedNodeId = ref("");
const nodeConfigText = ref("{}");
const newNodeType = ref("hitl_approval");
const centerTab = ref("workspace");
const runResult = ref(null);
const trace = ref(null);
const liveNodeStatuses = ref({});
const result = ref(null);
const status = ref("idle");
const error = ref("");
const saveMessage = ref("");
const copyMessage = ref("");
const workflowSocket = ref(null);
const workflowSocketClosing = ref(false);
const drawerMode = ref(null);
const historyDrawerOpen = ref(false);
const historyItems = ref([]);
const historyLoading = ref(false);
const selectedHistoryThreadId = ref("");
const pageMode = ref("creator");
const inspirationItems = [
  { label: "雨夜与思念", prompt: "下雨的夜晚，我忽然想起很久没有见面的故人。" },
  { label: "夏日公路", prompt: "盛夏傍晚开车离开熟悉的城市，既自由又有一点不舍。" },
  { label: "重新出发", prompt: "一段关系结束以后，终于鼓起勇气重新开始生活。" },
];
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
  { id: "brief", label: "02 歌曲简报", nodeIds: ["build_song_brief"] },
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

const creatorStageDefinitions = [
  { id: "understand", label: "理解需求", description: "提取故事、情绪与表达方向", nodeIds: ["validate_request", "parse_intent"] },
  {
    id: "compose",
    label: "构思",
    description: "设计歌曲简报、风格、Hook 与结构",
    nodeIds: ["build_song_brief", "plan_music_style", "hook_lab", "draft_structure_blueprints", "critique_structure"],
  },
  { id: "write", label: "写作", description: "生成完整歌词", nodeIds: ["plan_style_prompt", "generate_lyrics"] },
  {
    id: "polish",
    label: "润色",
    description: "检查质量、修复格式并确定歌名",
    nodeIds: ["review_quality", "repair_lyrics", "normalize_suno_format", "refine_title"],
  },
  { id: "complete", label: "完成", description: "整理最终交付", nodeIds: ["build_response", "final_review", "done"] },
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
  executing: "运行中",
  repairing: "自修复中",
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
const orderedFlowNodes = computed(() => flowGroups.value.flatMap((group) => group.nodes));

const traceNodes = computed(() => trace.value?.nodes ?? runResult.value?.trace?.nodes ?? []);
const completedIds = computed(() => {
  return new Set(traceNodes.value.filter((node) => node.status === "completed").map((node) => node.node_id));
});
const waitingNodeId = computed(() => runResult.value?.waiting?.node_id ?? "");
const isWorkflowExecuting = computed(() => {
  return status.value === "running" || status.value.startsWith("resume-");
});
const hasLiveWaitingAction = computed(() => {
  return Array.isArray(runResult.value?.waiting?.actions) && runResult.value.waiting.actions.length > 0;
});
const isWorkflowBusy = computed(() => {
  return status.value !== "idle" || isWorkflowExecuting.value || hasLiveWaitingAction.value;
});
const currentExecutingNodeId = computed(() => {
  if (!isWorkflowExecuting.value || waitingNodeId.value) return "";
  const nextNode = orderedFlowNodes.value.find((node) => !completedIds.value.has(node.id));
  return nextNode?.id ?? "";
});

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

const focusNodeId = computed(() => {
  if (userSelectedNodeId.value) return userSelectedNodeId.value;
  return currentExecutingNodeId.value || waitingNodeId.value || selectedNodeId.value;
});
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
const creatorProgressStages = computed(() => {
  return creatorStageDefinitions.map((stage) => {
    const statuses = stage.nodeIds.map((nodeId) => nodeStatus(nodeId));
    let stageStatus = "pending";
    if (statuses.includes("waiting")) {
      stageStatus = "waiting";
    } else if (statuses.includes("executing") || statuses.includes("repairing")) {
      stageStatus = "active";
    } else if (statuses.length > 0 && statuses.every((item) => item === "completed")) {
      stageStatus = "completed";
    }
    return { ...stage, status: stageStatus };
  });
});
const activeCreatorStage = computed(() => {
  return creatorProgressStages.value.find((stage) => stage.status === "waiting" || stage.status === "active") ?? null;
});
const activeCreatorStageNumber = computed(() => {
  if (finalDelivery.value) return 5;
  const activeIndex = creatorProgressStages.value.findIndex(
    (stage) => stage.status === "waiting" || stage.status === "active",
  );
  if (activeIndex >= 0) return activeIndex + 1;
  if (!hasRunStarted.value) return 0;
  const completedStages = creatorProgressStages.value.filter((stage) => stage.status === "completed").length;
  return Math.min(completedStages + 1, 5);
});
const creatorRunHeadline = computed(() => {
  if (displayError.value) return "创作未完成";
  if (finalDelivery.value) return "作品已经完成";
  if (activeCreatorStage.value?.status === "waiting") return "需要你的决定";
  if (activeCreatorStage.value) return `正在${activeCreatorStage.value.label}`;
  if (hasRunStarted.value) return "正在准备创作";
  return "准备开始";
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
const displayError = computed(() => formatUserError(error.value));
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

function workflowTarget() {
  return selectedApiTarget();
}

function workflowTargetLabel(target = workflowTarget()) {
  return environment.options.find((item) => item.value === target)?.label ?? target;
}

function targetUnavailableMessage(target = workflowTarget()) {
  const detail = environment.targetHealthDetail(target);
  return `${workflowTargetLabel(target)}服务未连接，无法继续工作流操作：${detail}。请启动对应服务后重试。`;
}

async function ensureWorkflowTargetOnline() {
  const target = workflowTarget();
  const currentHealth = environment.targetHealth(target);
  if (currentHealth === "online") return target;
  if (currentHealth === "offline") {
    throw new Error(targetUnavailableMessage(target));
  }
  const nextHealth = await environment.checkHealth(target);
  if (nextHealth !== "online") {
    throw new Error(targetUnavailableMessage(target));
  }
  return target;
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
    if (status.value === nextStatus) {
      status.value = "idle";
    }
  }
}

async function loadTemplate() {
  await withBusy("loading-template", async () => {
    await ensureWorkflowTargetOnline();
    template.value = await requestWorkflowJson(`/api/workflows/${workflowId}/template`, { target: workflowTarget() });
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

function formatUserError(rawError) {
  if (!rawError) return "";
  if (rawError.includes("OpenAI text inference failed") || rawError.includes("YTS_OPENAI_BASE_URL")) {
    return "OpenAI 接口请求失败：请检查 API Base URL 是否指向 /v1 接口，并确认模型服务可用。";
  }
  return rawError;
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
    result.value = null;
    trace.value = null;
    liveNodeStatuses.value = {};
    runResult.value = null;
    userSelectedNodeId.value = "";
    await ensureWorkflowTargetOnline();
    await streamWorkflow(`/api/workflows/${workflowId}/threads/stream`, {
      type: "run",
      thread_id: threadId.value,
      user_prompt: prompt.value,
      node_config: buildNodeConfigPayload(),
    });
  });
}

async function resumeThread(action) {
  const waiting = runResult.value?.waiting;
  if (!waiting) {
    error.value = "当前没有等待恢复的节点";
    return;
  }
  await withBusy(`resume-${action}`, async () => {
    userSelectedNodeId.value = "";
    liveNodeStatuses.value = {};
    runResult.value = {
      ...runResult.value,
      waiting: null,
      status: "waiting",
    };
    await ensureWorkflowTargetOnline();
    await streamWorkflow(`/api/workflows/${workflowId}/threads/${threadId.value}/stream`, {
      type: "resume",
      node_id: waiting.node_id,
      action,
      patch: action === "edit" ? parseNodeConfig() : {},
    });
  });
}

function streamWorkflow(path, payload) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const fallbackJson = () => fallbackWorkflowRequest(path, payload);
    const ws = openJsonStream(
      path,
      payload,
      {
        onMessage: (message, socket) => {
          if (message.type === "started") return;
          if (message.type === "trace") {
            applyWorkflowTrace(message.trace);
            return;
          }
          if (message.type === "node_status") {
            applyWorkflowNodeStatus(message);
            return;
          }
          if (message.type === "result") {
            applyWorkflowResult(message.result);
            settled = true;
            resolve(message.result);
            workflowSocket.value = null;
            socket.close();
            return;
          }
          if (message.type === "error") {
            settled = true;
            reject(new Error(message.detail || "工作流流式执行失败"));
            workflowSocket.value = null;
            socket.close();
            return;
          }
          settled = true;
          reject(new Error(`未知工作流流式消息: ${message.type}`));
          workflowSocket.value = null;
          socket.close();
        },
        onFallbackResult: (fallbackResult) => {
          applyWorkflowResult(fallbackResult);
          settled = true;
          workflowSocket.value = null;
          resolve(fallbackResult);
        },
        onError: (streamError) => {
          if (!settled) {
            settled = true;
            workflowSocket.value = null;
            reject(streamError);
          }
        },
        onClose: (socket) => {
          if (workflowSocket.value === socket) {
            workflowSocket.value = null;
          }
          if (workflowSocketClosing.value) {
            workflowSocketClosing.value = false;
            if (!settled) {
              settled = true;
              resolve(null);
            }
            return;
          }
          if (!settled) {
            settled = true;
            reject(new Error("工作流 WebSocket 连接已中断"));
          }
        },
      },
      {
        target: workflowTarget(),
        fallbackJson,
      },
    );
    workflowSocket.value = ws;
  });
}

function fallbackWorkflowRequest(path, payload) {
  if (payload.type === "run") {
    return requestWorkflowJson(`/api/workflows/${workflowId}/threads`, {
      method: "POST",
      target: workflowTarget(),
      body: JSON.stringify({
        thread_id: payload.thread_id,
        user_prompt: payload.user_prompt,
        node_config: payload.node_config,
      }),
    });
  }
  if (payload.type === "resume") {
    return requestWorkflowJson(`/api/workflows/${workflowId}/threads/${threadId.value}/resume`, {
      method: "POST",
      target: workflowTarget(),
      body: JSON.stringify({
        node_id: payload.node_id,
        action: payload.action,
        patch: payload.patch,
      }),
    });
  }
  throw new Error(`未知工作流 fallback 类型: ${payload.type}; path=${path}`);
}

function applyWorkflowTrace(nextTrace) {
  if (!nextTrace) return;
  trace.value = nextTrace;
  clearTerminalLiveNodeStatuses(nextTrace.nodes ?? []);
  runResult.value = {
    ...(runResult.value ?? {}),
    workflow_id: nextTrace.workflow_id,
    thread_id: nextTrace.thread_id,
    run_id: nextTrace.run_id,
    trace: nextTrace,
  };
}

function applyWorkflowNodeStatus(message) {
  const nodeId = typeof message?.node_id === "string" ? message.node_id.trim() : "";
  const liveStatus = typeof message?.status === "string" ? message.status.trim() : "";
  if (!nodeId || !liveStatus) {
    throw new Error("工作流节点状态消息缺少 node_id 或 status");
  }
  liveNodeStatuses.value = {
    ...liveNodeStatuses.value,
    [nodeId]: liveStatus,
  };
  if (!userSelectedNodeId.value) {
    selectedNodeId.value = nodeId;
  }
}

function applyWorkflowResult(nextResult) {
  runResult.value = nextResult;
  trace.value = nextResult.trace;
  result.value = nextResult.output;
  liveNodeStatuses.value = {};
}

async function refreshTrace() {
  await withBusy("trace", async () => {
    await ensureWorkflowTargetOnline();
    trace.value = await requestWorkflowJson(`/api/workflows/${workflowId}/threads/${threadId.value}/trace`, { target: workflowTarget() });
  });
}

async function openHistoryDrawer() {
  historyDrawerOpen.value = true;
  await loadHistoryItems();
}

function closeHistoryDrawer() {
  historyDrawerOpen.value = false;
}

function startNewCreation() {
  if (isWorkflowBusy.value) {
    error.value = "当前创作仍在进行，完成后才能开始新的创作";
    return;
  }
  threadId.value = `workflow-${Date.now()}`;
  prompt.value = "";
  runResult.value = null;
  trace.value = null;
  liveNodeStatuses.value = {};
  result.value = null;
  error.value = "";
  saveMessage.value = "";
  copyMessage.value = "";
  selectedHistoryThreadId.value = "";
  userSelectedNodeId.value = "";
}

function applyInspiration(nextPrompt) {
  if (typeof nextPrompt !== "string" || !nextPrompt.trim()) {
    throw new Error("灵感提示必须包含创作内容");
  }
  prompt.value = nextPrompt;
}

async function loadHistoryItems() {
  historyLoading.value = true;
  error.value = "";
  try {
    await ensureWorkflowTargetOnline();
    historyItems.value = await listWorkflowHistory(workflowId, { target: workflowTarget() });
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    historyLoading.value = false;
  }
}

async function selectHistoryItem(item) {
  selectedHistoryThreadId.value = item.thread_id;
  error.value = "";
  copyMessage.value = "";
  try {
    await ensureWorkflowTargetOnline();
    const selectedResult = await getWorkflowRunResult(workflowId, item.thread_id, { target: workflowTarget() });
    const replayWaiting = selectedResult.waiting
      ? { ...selectedResult.waiting, actions: [] }
      : null;
    threadId.value = item.thread_id;
    prompt.value = item.user_prompt;
    trace.value = selectedResult.trace;
    result.value = selectedResult.output;
    runResult.value = {
      ...selectedResult,
      waiting: replayWaiting,
    };
    userSelectedNodeId.value = focusNodeIdFromTrace(selectedResult.trace);
    selectedNodeId.value = userSelectedNodeId.value || draftTemplate.value?.start_node_id || selectedNodeId.value;
    centerTab.value = "workspace";
    historyDrawerOpen.value = false;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function saveFinalDeliveryToAssets() {
  if (!finalDelivery.value) {
    error.value = "当前没有可保存的最终结果";
    return;
  }
  saveMessage.value = "";
  await withBusy("saving-asset", async () => {
    await ensureWorkflowTargetOnline();
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

async function copyDeliveryText(text, label) {
  if (typeof text !== "string" || !text.trim()) {
    error.value = `${label}没有可复制的内容`;
    return;
  }
  error.value = "";
  copyMessage.value = "";
  try {
    await navigator.clipboard.writeText(text);
    copyMessage.value = `已复制${label}`;
  } catch (err) {
    error.value = `${label}复制失败：${err instanceof Error ? err.message : String(err)}`;
  }
}

function selectNode(nodeId) {
  selectedNodeId.value = nodeId;
  userSelectedNodeId.value = nodeId;
  resetSelectedNodeConfig();
  centerTab.value = "workspace";
}

function openDrawer(mode) {
  drawerMode.value = mode;
}

function closeDrawer() {
  drawerMode.value = null;
}

function focusNodeIdFromTrace(selectedTrace) {
  const nodes = selectedTrace.nodes ?? [];
  const contentNode = [...nodes].reverse().find((node) => hasArtifactValue(node.artifact_preview));
  return contentNode?.node_id ?? nodes[nodes.length - 1]?.node_id ?? "";
}

function onNodeClick(event) {
  selectNode(event.node.id);
}

function nodeStatus(nodeId) {
  const liveStatus = liveNodeStatuses.value[nodeId];
  if (liveStatus) return liveStatus;
  if (currentExecutingNodeId.value === nodeId) return "executing";
  if (waitingNodeId.value === nodeId) return "waiting";
  if (completedIds.value.has(nodeId)) return "completed";
  return "idle";
}

function clearTerminalLiveNodeStatuses(nodes) {
  const next = { ...liveNodeStatuses.value };
  for (const node of nodes) {
    if (node.status === "completed" || node.status === "waiting") {
      delete next[node.node_id];
    }
  }
  liveNodeStatuses.value = next;
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

function formatHistoryTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return `时间格式错误：${value}`;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
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

watch(isWorkflowBusy, () => {
  environment.setSwitchLocked(isWorkflowBusy.value);
});

function handleApiTargetChanged() {
  if (workflowSocket.value) {
    workflowSocketClosing.value = true;
    workflowSocket.value.close();
    workflowSocket.value = null;
  }
  runResult.value = null;
  trace.value = null;
  liveNodeStatuses.value = {};
  result.value = null;
  error.value = "";
  status.value = "idle";
  userSelectedNodeId.value = "";
  void loadTemplate();
}

onMounted(() => {
  window.addEventListener(API_TARGET_CHANGED_EVENT, handleApiTargetChanged);
  environment.setSwitchLocked(isWorkflowBusy.value);
  void loadTemplate();
  void loadHistoryItems();
});
onUnmounted(() => {
  window.removeEventListener(API_TARGET_CHANGED_EVENT, handleApiTargetChanged);
  environment.setSwitchLocked(false);
  if (workflowSocket.value) {
    workflowSocketClosing.value = true;
    workflowSocket.value.close();
    workflowSocket.value = null;
  }
});
</script>

<template>
  <main class="creator-page">
    <section v-if="pageMode === 'creator'" class="creator-mode">
      <aside class="creation-session-sidebar">
        <header class="session-title">创作记录</header>
        <button class="new-creation-button" type="button" :disabled="isWorkflowBusy" @click="startNewCreation">
          <Plus :size="16" />
          新创作
        </button>
        <div class="session-list-head">
          <span>最近创作</span>
          <button type="button" title="刷新历史创作" :disabled="historyLoading" @click="loadHistoryItems">
            <RefreshCw :size="14" />
          </button>
        </div>
        <div class="session-list">
          <p v-if="historyLoading" class="session-empty">正在加载历史创作</p>
          <p v-else-if="!historyItems.length" class="session-empty">还没有历史创作</p>
          <button
            v-for="item in historyItems"
            v-else
            :key="item.thread_id"
            :class="['session-row', selectedHistoryThreadId === item.thread_id ? 'active' : '']"
            type="button"
            @click="selectHistoryItem(item)"
          >
            <MessageSquare :size="15" />
            <span><strong>{{ item.title }}</strong><small>{{ item.user_prompt }}</small></span>
            <time :datetime="item.updated_at">{{ formatHistoryTime(item.updated_at) }}</time>
          </button>
        </div>
        <button class="advanced-mode-link" type="button" @click="pageMode = 'advanced'">
          <Settings2 :size="15" />
          高级模式
        </button>
      </aside>

      <section :class="['creator-conversation', { 'is-empty': !hasRunStarted, 'is-completed': Boolean(finalDelivery) }]">
        <header v-if="!finalDelivery" class="creator-header">
          <h1>{{ finalDelivery?.title ?? "创作" }}</h1>
        </header>

        <div v-if="hasRunStarted" class="creation-feed">
          <article class="prompt-entry">
            <div class="manuscript-quote">
              <div class="feed-entry-label"><FileText :size="14" /> 你的创作想法</div>
              <p>{{ prompt }}</p>
            </div>
          </article>

          <section v-if="!finalDelivery" class="creator-progress" aria-label="创作进度" aria-live="polite">
            <section v-if="activeCreatorStage" class="progress-summary">
              <span class="active-stage-signal"><span></span></span>
              <div>
                <strong>{{ creatorRunHeadline }}</strong>
                <p>{{ activeCreatorStage.description }}</p>
              </div>
              <em>{{ activeCreatorStageNumber }}/5</em>
            </section>
            <ol>
              <li
                v-for="stage in creatorProgressStages"
                :key="stage.id"
                :class="[`stage-${stage.status}`]"
              >
                <span class="creator-stage-marker">
                  <CheckCircle2 v-if="stage.status === 'completed'" :size="15" />
                  <Circle v-else :size="12" />
                </span>
                <span><strong>{{ stage.label }}</strong></span>
              </li>
            </ol>
          </section>

          <p v-if="displayError" class="error-box compact-error" role="alert">{{ displayError }}</p>

          <section
            v-if="hasLiveWaitingAction && focusNode?.id === runResult.waiting.node_id"
            class="creator-decision"
          >
            <span class="decision-mark"><Hand :size="17" /></span>
            <div><strong>需要你的决定</strong><p>{{ runResult.waiting.prompt }}</p></div>
            <div class="decision-actions">
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
          </section>

          <article v-if="finalDelivery" class="completed-work">
            <header class="completed-work-head">
              <div class="completed-work-title">
                <span><CheckCircle2 :size="14" /> 创作完成</span>
                <h2>{{ finalDelivery.title }}</h2>
              </div>
              <div class="completed-work-actions">
                <button class="primary-button" type="button" :disabled="status !== 'idle'" @click="saveFinalDeliveryToAssets">
                  <Save :size="15" /> 保存到资产
                </button>
              </div>
            </header>
            <section class="completed-style">
              <div class="completed-field-label">
                <span>Style Prompt</span>
                <button type="button" title="复制 Style Prompt" @click="copyDeliveryText(finalDelivery.style, 'Style Prompt')">
                  <Copy :size="14" />
                </button>
              </div>
              <p>{{ finalDelivery.style || "暂无 Style Prompt" }}</p>
            </section>
            <section class="completed-lyrics">
              <div class="completed-field-label">
                <span>歌词</span>
                <button type="button" title="复制歌词" @click="copyDeliveryText(finalDelivery.lyrics, '歌词')">
                  <Copy :size="14" />
                </button>
              </div>
              <pre>{{ finalDelivery.lyrics || "暂无歌词" }}</pre>
            </section>
            <p v-if="saveMessage" class="save-message">{{ saveMessage }}</p>
            <p v-if="copyMessage" class="copy-message" role="status">{{ copyMessage }}</p>
          </article>
        </div>

        <footer v-if="!hasRunStarted && !isWorkflowExecuting" :class="['composer-dock', { 'is-empty': !hasRunStarted }]">
          <div v-if="!hasRunStarted" class="empty-composer-intro">
            <span class="empty-spark"><Sparkles :size="20" /></span>
            <h2>今天想写一首什么歌？</h2>
            <p>写下一个画面、一段关系，或此刻最想表达的情绪。</p>
          </div>
          <div class="creator-composer">
            <textarea
              v-model="prompt"
              :disabled="isWorkflowBusy"
              rows="2"
              maxlength="1000"
              placeholder="例如：下雨的午后，我忽然想起很久没见的故人。"
            ></textarea>
            <div class="composer-toolbar">
              <span class="composer-mode" title="当前创作模式">
                <Sparkles :size="15" />
                歌词创作
              </span>
              <span>通常 1–2 句话就够了</span>
              <button
                class="composer-submit"
                type="button"
                title="开始创作"
                :disabled="!prompt.trim() || isWorkflowBusy"
                @click="runThread"
              >
                <ArrowUp :size="18" />
              </button>
            </div>
          </div>
          <div class="inspiration-row">
            <span>试试这些方向</span>
            <button
              v-for="item in inspirationItems"
              :key="item.label"
              type="button"
              :disabled="isWorkflowBusy"
              @click="applyInspiration(item.prompt)"
            >
              {{ item.label }}
            </button>
          </div>
        </footer>
      </section>

    </section>

    <section v-else class="advanced-workspace">
      <div class="app-shell">
    <aside class="left-rail">
      <div class="brand-block">
        <div class="brand-mark"><Workflow :size="18" /></div>
        <div>
          <h1>乐兔工作室</h1>
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
          <button class="icon-button" type="button" title="重新加载模板" @click="loadTemplate">
            <RefreshCw :size="17" />
          </button>
          <button class="icon-button" type="button" title="运行输入" @click="openDrawer('run')">
            <SquarePen :size="17" />
          </button>
          <button class="icon-button" type="button" title="节点配置" @click="openDrawer('config')">
            <Settings2 :size="17" />
          </button>
          <button class="secondary-action" type="button" title="历史创作" @click="openHistoryDrawer">
            <History :size="16" />
            历史
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

        <p v-if="displayError" class="error-box advanced-compact-error">{{ displayError }}</p>
        <div v-if="hasLiveWaitingAction && focusNode?.id === runResult.waiting.node_id" class="workspace-gate compact-gate">
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

    <Transition name="drawer-slide">
      <div v-if="historyDrawerOpen" class="drawer-backdrop" @click.self="closeHistoryDrawer">
        <aside class="side-drawer history-drawer" aria-label="历史创作列表">
          <header class="drawer-head">
            <div class="drawer-titleline">
              <span class="eyebrow">创作回放</span>
              <h3>历史</h3>
            </div>
            <button class="icon-button" type="button" title="关闭" @click="closeHistoryDrawer">×</button>
          </header>

          <div class="history-toolbar">
            <button type="button" :disabled="historyLoading" @click="loadHistoryItems">
              <RefreshCw :size="15" />
              刷新
            </button>
          </div>

          <div class="history-content">
            <div v-if="historyLoading" class="workspace-note">正在加载历史创作。</div>
            <div v-else-if="!historyItems.length" class="workspace-note">暂无历史创作。</div>
            <div v-else class="history-list">
              <button
                v-for="item in historyItems"
                :key="item.thread_id"
                :class="{ active: selectedHistoryThreadId === item.thread_id }"
                type="button"
                @click="selectHistoryItem(item)"
              >
                <span class="history-main">
                  <strong>{{ item.title }}</strong>
                  <small>{{ item.user_prompt }}</small>
                </span>
                <span class="history-meta">
                  <time :datetime="item.updated_at">{{ formatHistoryTime(item.updated_at) }}</time>
                  <em>{{ item.completed_nodes }}/{{ item.total_nodes }}</em>
                </span>
              </button>
            </div>
          </div>
        </aside>
      </div>
    </Transition>
      </div>
    </section>
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
  min-width: 320px;
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

.creator-page {
  min-height: 100vh;
}

.creator-mode {
  background: #070c14;
  display: grid;
  grid-template-columns: 208px minmax(0, 1fr);
  height: 100vh;
  min-width: 0;
}

.creation-session-sidebar {
  background: #091522;
  border-right: 1px solid var(--color-border-soft);
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 16px 10px 12px;
}

.session-row > span {
  display: grid;
  min-width: 0;
}

.session-title {
  color: var(--color-heading);
  font-size: 13px;
  font-weight: 700;
  padding: 2px 7px 14px;
}

.session-row small,
.session-row time,
.session-empty {
  color: var(--color-muted);
  font-size: 10px;
}

.new-creation-button {
  background: transparent;
  border-color: rgba(125, 211, 252, 0.16);
  color: var(--color-heading);
  justify-content: flex-start;
  min-height: 36px;
  width: 100%;
}

.new-creation-button:hover,
.new-creation-button:focus-visible {
  background: rgba(14, 165, 233, 0.1);
  border-color: rgba(34, 211, 238, 0.34);
}

.session-list-head {
  align-items: center;
  color: var(--color-muted);
  display: flex;
  font-size: 10px;
  font-weight: 700;
  justify-content: space-between;
  padding: 20px 7px 8px;
}

.session-list-head button {
  background: transparent;
  border: 0;
  color: var(--color-muted);
  min-height: 26px;
  padding: 0;
  width: 26px;
}

.session-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.session-empty {
  margin: 8px 7px;
}

.session-row {
  background: transparent;
  border: 0;
  border-radius: 6px;
  display: grid;
  gap: 8px;
  grid-template-columns: 16px minmax(0, 1fr);
  justify-content: stretch;
  margin-bottom: 3px;
  min-height: 48px;
  padding: 7px;
  text-align: left;
  width: 100%;
}

.session-row:hover,
.session-row.active {
  background: rgba(14, 165, 233, 0.12);
  box-shadow: inset 2px 0 0 var(--color-brand-cyan);
}

.session-row > svg {
  color: var(--color-muted);
  margin-top: 2px;
}

.session-row strong,
.session-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-row strong {
  color: var(--color-text);
  font-size: 12px;
  font-weight: 650;
}

.session-row time {
  grid-column: 2;
}

.advanced-mode-link {
  background: transparent;
  border: 0;
  color: var(--color-muted);
  justify-content: flex-start;
  margin-top: 8px;
}

.creator-conversation {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-height: 0;
  min-width: 0;
}

.creator-conversation.is-empty {
  grid-template-rows: auto minmax(0, 1fr);
}

.creator-conversation.is-completed {
  grid-template-rows: minmax(0, 1fr);
}

.creator-header {
  align-items: center;
  border-bottom: 1px solid var(--color-border-soft);
  display: flex;
  justify-content: space-between;
  margin: 0 24px;
  min-height: 56px;
}

.creator-header h1 {
  color: var(--color-heading);
  font-size: 15px;
  font-weight: 700;
  margin: 0;
}

.creation-feed {
  margin: 0 auto;
  max-width: 780px;
  min-height: 0;
  overflow-y: auto;
  padding: 30px 24px 42px;
  width: 100%;
}

.empty-spark {
  color: var(--color-brand-green);
  filter: drop-shadow(0 0 8px var(--color-brand-glow));
}

.empty-composer-intro {
  margin: 0 auto 22px;
  max-width: 720px;
  text-align: left;
  width: 100%;
}

.empty-composer-intro .empty-spark {
  display: inline-flex;
  margin-bottom: 12px;
}

.empty-composer-intro h2 {
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 8px;
}

.empty-composer-intro p {
  color: #7890a5;
  font-size: 13px;
  margin: 0;
}

.prompt-entry,
.creator-progress,
.creator-decision {
  border-top: 1px solid var(--color-border-soft);
  margin-bottom: 28px;
  padding-top: 16px;
}

.prompt-entry {
  border-top: 0;
  padding-top: 0;
}

.manuscript-quote {
  border-left: 2px solid rgba(99, 215, 199, 0.56);
  max-width: 680px;
  padding: 3px 0 3px 18px;
}

.feed-entry-label {
  align-items: center;
  color: var(--color-muted);
  display: flex;
  font-size: 10px;
  font-weight: 700;
  gap: 6px;
}

.manuscript-quote p {
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  color: #e6e3dc;
  display: -webkit-box;
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: 15px;
  line-height: 1.75;
  margin: 10px 0 0;
  overflow: hidden;
}

.progress-summary {
  align-items: center;
  display: grid;
  gap: 11px;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  padding: 2px 0 15px;
}

.active-stage-signal {
  align-items: center;
  display: inline-flex;
  height: 20px;
  justify-content: center;
  width: 20px;
}

.active-stage-signal > span {
  animation: creatorPulse 1.6s ease-in-out infinite;
  background: var(--color-brand-cyan);
  border-radius: 50%;
  box-shadow: 0 0 0 6px rgba(34, 211, 238, 0.07);
  height: 8px;
  width: 8px;
}

.progress-summary > div {
  display: grid;
  gap: 2px;
}

.progress-summary p {
  color: #7890a5;
  font-size: 11px;
}

.progress-summary strong {
  color: var(--color-heading);
  font-size: 14px;
}

.progress-summary p {
  margin: 0;
}

.progress-summary em {
  color: var(--color-brand-cyan);
  font-size: 11px;
  font-style: normal;
  font-variant-numeric: tabular-nums;
}

.creator-progress ol {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  list-style: none;
  border-top: 1px solid var(--color-border-soft);
  margin: 0;
  padding-top: 14px;
}

.creator-progress li {
  display: grid;
  gap: 7px;
  grid-template-columns: 18px minmax(0, 1fr);
  min-width: 0;
  position: relative;
}

.creator-progress li strong {
  color: #7890a5;
  font-size: 11px;
  font-weight: 650;
}

.creator-progress li:not(:last-child)::after {
  background: var(--color-border-soft);
  content: "";
  height: 1px;
  left: 18px;
  position: absolute;
  right: 6px;
  top: 8px;
}

.creator-stage-marker {
  align-items: center;
  background: var(--color-bg);
  color: var(--color-muted);
  display: inline-flex;
  height: 17px;
  justify-content: center;
  position: relative;
  width: 17px;
  z-index: 1;
}

.creator-progress li.stage-completed .creator-stage-marker {
  color: var(--color-brand-green);
}

.creator-progress li.stage-active .creator-stage-marker,
.creator-progress li.stage-active strong {
  color: var(--color-brand-cyan);
}

.creator-progress li.stage-waiting .creator-stage-marker,
.creator-progress li.stage-waiting strong {
  color: #ff8e82;
}

.creator-decision {
  align-items: start;
  display: grid;
  gap: 12px;
  grid-template-columns: 34px minmax(0, 1fr) auto;
}

.decision-mark {
  align-items: center;
  background: rgba(255, 142, 130, 0.1);
  color: #ff8e82;
  display: inline-flex;
  height: 34px;
  justify-content: center;
  width: 34px;
}

.creator-decision strong {
  color: var(--color-heading);
  font-size: 13px;
}

.creator-decision p {
  color: var(--color-muted);
  font-size: 12px;
  line-height: 1.5;
  margin: 4px 0 0;
}

.decision-actions {
  display: flex;
  gap: 6px;
}

.completed-work {
  border-top: 1px solid rgba(99, 215, 199, 0.28);
  padding: 25px 0 72px;
}

.completed-work-head {
  align-items: end;
  display: flex;
  gap: 24px;
  justify-content: space-between;
  margin-bottom: 27px;
}

.completed-work-title > span {
  align-items: center;
  color: var(--color-brand-green);
  display: flex;
  font-size: 10px;
  font-weight: 700;
  gap: 6px;
}

.completed-work-title h2 {
  color: #f2eee5;
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: 30px;
  font-weight: 600;
  line-height: 1.25;
  margin: 8px 0 0;
}

.completed-work-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.completed-work-actions button:first-child {
  background: transparent;
  border-color: var(--color-border-soft);
}

.completed-style {
  border-bottom: 1px solid var(--color-border-soft);
  border-top: 1px solid var(--color-border-soft);
  display: grid;
  gap: 20px;
  grid-template-columns: 104px minmax(0, 1fr);
  padding: 16px 0;
}

.completed-field-label {
  align-items: center;
  align-self: start;
  display: flex;
  gap: 7px;
}

.completed-field-label > span {
  color: #7890a5;
  font-size: 10px;
  font-weight: 700;
}

.completed-field-label button {
  background: transparent;
  border: 0;
  color: #7890a5;
  height: 26px;
  min-height: 26px;
  padding: 0;
  width: 26px;
}

.completed-field-label button:hover,
.completed-field-label button:focus-visible {
  background: rgba(34, 211, 238, 0.08);
  color: var(--color-brand-cyan);
}

.completed-style p {
  color: #b8c9d8;
  font-size: 12px;
  line-height: 1.7;
  margin: 0;
}

.completed-lyrics {
  display: grid;
  gap: 20px;
  grid-template-columns: 104px minmax(0, 1fr);
  padding-top: 26px;
}

.completed-lyrics pre {
  color: #e6e3dc;
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: 15px;
  line-height: 2;
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.copy-message {
  color: var(--color-brand-green);
  font-size: 11px;
  margin: 14px 0 0;
  text-align: right;
}

.composer-dock {
  background: #070c14;
  padding: 18px 24px 20px;
}

.composer-dock.is-empty {
  align-content: center;
  align-self: stretch;
  background: transparent;
  display: grid;
  padding-bottom: 9vh;
}

.creator-composer,
.inspiration-row {
  margin: 0 auto;
  max-width: 720px;
}

.creator-composer {
  background: #0f1b28;
  border: 1px solid rgba(138, 164, 189, 0.22);
  border-radius: 22px;
  box-shadow: 0 18px 48px rgba(0, 5, 15, 0.32);
  max-width: 720px;
  padding: 16px 17px 13px;
  width: 100%;
}

.creator-composer:focus-within {
  border-color: rgba(34, 211, 238, 0.5);
  box-shadow: 0 18px 48px rgba(0, 5, 15, 0.32), 0 0 0 3px rgba(34, 211, 238, 0.06);
}

.creator-composer textarea {
  background: transparent;
  border: 0;
  color: var(--color-heading);
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: 14px;
  height: 64px;
  line-height: 1.65;
  max-height: 154px;
  outline: 0;
  padding: 0 2px;
  resize: none;
}

.composer-toolbar {
  align-items: center;
  display: flex;
  gap: 9px;
  margin-top: 8px;
}

.composer-mode {
  align-items: center;
  background: rgba(7, 20, 38, 0.35);
  border: 1px solid var(--color-border-soft);
  border-radius: 7px;
  border-color: var(--color-border-soft);
  color: var(--color-text);
  display: inline-flex;
  font-size: 11px;
  gap: 6px;
  min-height: 30px;
  padding: 0 9px;
}

.composer-mode svg:first-child {
  color: var(--color-brand-cyan);
}

.composer-toolbar > span {
  color: var(--color-muted);
  font-size: 10px;
}

.composer-submit {
  background: var(--color-brand-green);
  border: 0;
  border-radius: 50%;
  color: #05221d;
  height: 36px;
  margin-left: auto;
  min-height: 36px;
  padding: 0;
  width: 36px;
}

.composer-submit:disabled {
  background: #2b3d4f;
  color: #70869a;
}

.inspiration-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 5px 0;
}

.inspiration-row > span {
  color: var(--color-muted);
  font-size: 10px;
  margin-right: 3px;
}

.inspiration-row button {
  background: transparent;
  border-color: var(--color-border-soft);
  color: var(--color-muted);
  font-size: 10px;
  min-height: 27px;
  padding: 0 8px;
}

.save-message {
  color: var(--color-brand-green);
  font-size: 11px;
  margin: 10px 0 0;
  text-align: right;
}

.advanced-workspace {
  min-width: 1240px;
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
  filter: drop-shadow(0 0 7px var(--color-brand-glow));
  height: 34px;
  width: 34px;
}

.brand-mark svg {
  stroke: url(#yts-brand-gradient);
  color: var(--color-brand-cyan);
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
  --timeline-scrollbar-safe-zone: 14px;

  max-height: calc(100vh - 104px);
  overflow-x: hidden;
  overflow-y: auto;
  padding-right: var(--timeline-scrollbar-safe-zone);
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

.compact-list::-webkit-scrollbar {
  width: 7px;
}

.compact-list::-webkit-scrollbar-track {
  background: transparent;
}

.compact-list::-webkit-scrollbar-thumb {
  background: rgba(138, 164, 189, 0.28);
  background-clip: content-box;
  border: 2px solid transparent;
  border-radius: 999px;
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

.timeline-node.status-executing {
  animation: timelineBreathing 1.45s ease-in-out infinite;
  background: rgba(14, 165, 233, 0.12);
  box-shadow: inset 3px 0 0 var(--color-accent), 0 0 22px rgba(14, 165, 233, 0.2);
  color: var(--color-heading);
}

.timeline-node.status-repairing {
  animation: timelineBreathing 1.45s ease-in-out infinite;
  background: rgba(245, 158, 11, 0.13);
  box-shadow: inset 3px 0 0 var(--color-warning), 0 0 22px rgba(245, 158, 11, 0.18);
  color: var(--color-heading);
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

.timeline-dot::after {
  border-radius: 50%;
  content: "";
  inset: -7px;
  opacity: 0;
  position: absolute;
}

.timeline-node.status-executing .timeline-dot::after {
  animation: nodePulse 1.45s ease-out infinite;
  background: rgba(14, 165, 233, 0.34);
}

.timeline-node.status-repairing .timeline-dot::after {
  animation: nodePulse 1.45s ease-out infinite;
  background: rgba(245, 158, 11, 0.34);
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

.timeline-node.status-executing .timeline-status {
  background: var(--color-accent-soft);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.timeline-node.status-repairing .timeline-status {
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

.icon-button {
  width: 38px;
}

.primary-button {
  background: var(--color-accent-strong);
  border-color: var(--color-accent-strong);
  color: var(--color-heading);
}

.secondary-action {
  background: rgba(14, 165, 233, 0.1);
  border-color: var(--color-border-soft);
  color: var(--color-muted-strong);
  font-weight: 800;
}

.secondary-action:hover,
.secondary-action:focus-visible {
  background: rgba(14, 165, 233, 0.18);
  border-color: var(--color-accent);
  color: var(--color-accent);
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
  background: transparent;
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
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.08), rgba(16, 36, 58, 0.78));
  border-radius: 8px;
  box-shadow: inset 3px 0 0 rgba(14, 165, 233, 0.38), 0 12px 26px rgba(0, 8, 20, 0.14);
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

.status-badge.repairing {
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
  background: linear-gradient(180deg, rgba(16, 36, 58, 0.9), rgba(12, 30, 51, 0.82));
  border-radius: 8px;
  box-shadow: 0 12px 28px rgba(0, 8, 20, 0.12);
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
  align-content: start;
  grid-template-rows: repeat(2, minmax(0, max-content));
  min-width: 0;
}

.diagnostic-scroll,
.llm-code {
  min-height: 0;
  overflow: auto;
}

.llm-panel {
  align-content: stretch;
  grid-template-rows: auto max-content;
  height: max-content;
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
  max-height: min(38vh, 420px);
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

.workflow-node.status-executing {
  animation: nodeBreathing 1.45s ease-in-out infinite;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.15), 0 0 30px rgba(14, 165, 233, 0.22);
}

.workflow-node.status-repairing {
  animation: nodeBreathing 1.45s ease-in-out infinite;
  border-color: var(--color-warning);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.13), 0 0 30px rgba(245, 158, 11, 0.18);
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

.node-status[data-status="repairing"],
.trace-list span[data-status="repairing"] {
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

.history-drawer {
  grid-template-rows: auto auto minmax(0, 1fr);
}

.history-toolbar {
  align-items: center;
  display: flex;
  justify-content: flex-end;
  padding: 10px 0;
}

.history-content {
  min-height: 0;
  overflow: hidden;
}

.history-list {
  display: grid;
  gap: 5px;
  max-height: calc(100vh - 118px);
  overflow: auto;
}

.history-list button {
  align-items: center;
  background: rgba(9, 28, 48, 0.7);
  border: 0;
  border-radius: 7px;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) 96px;
  justify-content: stretch;
  min-height: 58px;
  padding: 9px 10px;
  text-align: left;
}

.history-list button:hover,
.history-list button:focus-visible,
.history-list button.active {
  background: rgba(14, 165, 233, 0.13);
  box-shadow: inset 3px 0 0 var(--color-accent);
  outline: 0;
}

.history-main {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.history-main strong,
.history-main small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-main strong {
  color: var(--color-heading);
  font-size: 13px;
  font-weight: 850;
}

.history-main small,
.history-meta {
  color: var(--color-muted);
  font-size: 11px;
}

.history-meta {
  display: grid;
  gap: 5px;
  justify-items: end;
}

.history-meta time {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.history-meta em {
  background: var(--color-panel);
  border-radius: 999px;
  color: var(--color-muted-strong);
  font-style: normal;
  line-height: 1;
  padding: 4px 7px;
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

@keyframes timelineBreathing {
  0%,
  100% {
    box-shadow: inset 3px 0 0 rgba(14, 165, 233, 0.55), 0 0 12px rgba(14, 165, 233, 0.12);
  }
  50% {
    box-shadow: inset 3px 0 0 var(--color-accent), 0 0 28px rgba(14, 165, 233, 0.34);
  }
}

@keyframes nodePulse {
  0% {
    opacity: 0.62;
    transform: scale(0.68);
  }
  100% {
    opacity: 0;
    transform: scale(1.9);
  }
}

@keyframes nodeBreathing {
  0%,
  100% {
    box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.12), 0 8px 20px rgba(0, 8, 20, 0.12);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.2), 0 0 34px rgba(14, 165, 233, 0.28);
  }
}

@keyframes creatorPulse {
  0%,
  100% {
    opacity: 0.7;
    transform: scale(0.86);
  }
  50% {
    opacity: 1;
    transform: scale(1.08);
  }
}

@media (max-width: 900px) {
  .creation-session-sidebar {
    display: none;
  }

  .creator-mode {
    grid-template-columns: minmax(0, 1fr);
  }

  .creator-header {
    margin: 0 18px;
  }

  .creation-feed {
    padding: 26px 18px 36px;
  }

  .composer-dock {
    padding-inline: 14px;
  }

  .creator-progress ol {
    gap: 0;
    grid-template-columns: minmax(0, 1fr);
  }

  .creator-progress li {
    min-height: 46px;
  }

  .creator-progress li:not(:last-child)::after {
    bottom: 0;
    height: auto;
    left: 8px;
    right: auto;
    top: 20px;
    width: 1px;
  }

  .creator-decision {
    grid-template-columns: 34px minmax(0, 1fr);
  }

  .decision-actions {
    grid-column: 2;
  }

  .completed-work-head {
    align-items: stretch;
    flex-direction: column;
  }

  .completed-work-actions {
    width: 100%;
  }

  .completed-work-actions button {
    flex: 1 1 0;
  }

  .completed-style,
  .completed-lyrics {
    gap: 9px;
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .active-stage-signal > span,
  .timeline-node.status-executing,
  .timeline-node.status-executing .timeline-dot::after,
  .workflow-node.status-executing {
    animation: none;
  }
}
</style>
