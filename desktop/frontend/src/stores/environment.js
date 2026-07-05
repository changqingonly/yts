import { defineStore } from "pinia";
import {
  API_TARGET_CHANGED_EVENT,
  environmentOptions,
  selectedApiTarget,
  setSelectedApiTarget,
} from "../services/environment";

export const useEnvironmentStore = defineStore("environment", {
  state: () => ({
    target: selectedApiTarget(),
    options: environmentOptions(),
    switchLocked: false,
    targetChangedHandler: null,
    health: Object.fromEntries(environmentOptions().map((item) => [item.value, "unknown"])),
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
