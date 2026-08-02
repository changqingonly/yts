import { defineStore } from "pinia";
import { healthCheck } from "../services/transport";
import {
  API_TARGET_CHANGED_EVENT,
  assertApiTarget,
  environmentOptions,
  isTauriRuntime,
  selectedApiTarget,
  setSelectedApiTarget,
} from "../services/environment";
import { startSidecar } from "../services/desktop";

const pendingHealthChecks = new Map();
const LOCAL_HEALTH_RETRY_INTERVAL_MS = 800;
const LOCAL_HEALTH_RETRY_TIMEOUT_MS = 30000;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export const useEnvironmentStore = defineStore("environment", {
  state: () => ({
    target: selectedApiTarget(),
    options: environmentOptions(),
    switchLocked: false,
    targetChangedHandler: null,
    health: Object.fromEntries(environmentOptions().map((item) => [item.value, "unknown"])),
    healthError: Object.fromEntries(environmentOptions().map((item) => [item.value, ""])),
  }),
  actions: {
    setTarget(nextTarget) {
      if (this.switchLocked) {
        throw new Error("当前任务运行中，不能切换环境");
      }
      setSelectedApiTarget(nextTarget);
      this.target = nextTarget;
    },
    setSwitchLocked(locked) {
      this.switchLocked = Boolean(locked);
    },
    targetHealth(target) {
      return this.health[target] ?? "unknown";
    },
    targetHealthDetail(target) {
      const status = this.targetHealth(target);
      if (status === "online") return "已连接";
      if (status === "checking") return "检查中";
      if (status === "offline") {
        const reason = this.healthError[target];
        return reason ? `连接失败：${reason}` : "连接失败";
      }
      return "未检查";
    },
    /** 健康检查只负责承载 API/曲库的 sidecar。推理 gateway 启动会加载大模型，必须留在
     * 显式生成操作的边界，不能进入音乐播放和普通页面加载的关键路径。 */
    async checkHealth(target = this.target) {
      const requestTarget = assertApiTarget(target);
      if (pendingHealthChecks.has(requestTarget)) {
        return pendingHealthChecks.get(requestTarget);
      }
      this.health[requestTarget] = "checking";
      this.healthError[requestTarget] = "";
      const shouldRetry = requestTarget === "local" && isTauriRuntime();
      const healthPromise = (async () => {
        if (shouldRetry) {
          void startSidecar().catch(() => {});
        }
        const deadline = Date.now() + (shouldRetry ? LOCAL_HEALTH_RETRY_TIMEOUT_MS : 0);
        try {
          for (;;) {
            try {
              await healthCheck(requestTarget);
              this.health[requestTarget] = "online";
              return "online";
            } catch (error) {
              if (Date.now() >= deadline) {
                this.health[requestTarget] = "offline";
                this.healthError[requestTarget] = error instanceof Error ? error.message : String(error);
                return "offline";
              }
              await wait(LOCAL_HEALTH_RETRY_INTERVAL_MS);
            }
          }
        } finally {
          pendingHealthChecks.delete(requestTarget);
        }
      })();
      pendingHealthChecks.set(requestTarget, healthPromise);
      return healthPromise;
    },
    syncFromStorage() {
      this.target = selectedApiTarget();
    },
    handleTargetChanged(event) {
      this.target = event.detail?.target ?? selectedApiTarget();
    },
    attach() {
      if (!this.targetChangedHandler) {
        this.targetChangedHandler = (event) => this.handleTargetChanged(event);
      }
      window.addEventListener(API_TARGET_CHANGED_EVENT, this.targetChangedHandler);
    },
    detach() {
      if (this.targetChangedHandler) {
        window.removeEventListener(API_TARGET_CHANGED_EVENT, this.targetChangedHandler);
      }
    },
  },
});
