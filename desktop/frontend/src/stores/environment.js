import { defineStore } from "pinia";
import { healthCheck } from "../services/transport";
import {
  API_TARGET_CHANGED_EVENT,
  assertApiTarget,
  environmentOptions,
  selectedApiTarget,
  setSelectedApiTarget,
} from "../services/environment";

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
    async checkHealth(target = this.target) {
      const requestTarget = assertApiTarget(target);
      if (pendingHealthChecks.has(requestTarget)) {
        return pendingHealthChecks.get(requestTarget);
      }
      this.health[requestTarget] = "checking";
      this.healthError[requestTarget] = "";
      const healthPromise = (async () => {
        try {
          await healthCheck(requestTarget);
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
