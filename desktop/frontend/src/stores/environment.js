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
import { startLocalPlayback } from "../services/localStartup";

const pendingHealthChecks = new Map();
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
    /** 本地健康状态复用播放协调器的 sidecar/health Promise；推理 gateway 只允许由显式
     * 生成操作启动，不能进入音乐播放和普通页面加载的关键路径。 */
    async checkHealth(target = this.target) {
      const requestTarget = assertApiTarget(target);
      if (pendingHealthChecks.has(requestTarget)) {
        return pendingHealthChecks.get(requestTarget);
      }
      this.health[requestTarget] = "checking";
      this.healthError[requestTarget] = "";
      const shouldRetry = requestTarget === "local" && isTauriRuntime();
      const healthPromise = (async () => {
        try {
          if (shouldRetry) {
            await startLocalPlayback({ target: requestTarget, prepare: async () => {} });
          } else {
            await healthCheck(requestTarget);
          }
          this.health[requestTarget] = "online";
          return "online";
        } catch (error) {
          this.health[requestTarget] = "offline";
          this.healthError[requestTarget] = error instanceof Error ? error.message : String(error);
          return "offline";
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
