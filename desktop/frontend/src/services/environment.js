export const API_TARGET_CHANGED_EVENT = "yts-target-changed";
export const ENVIRONMENT_STORAGE_KEY = "yts-target";

const TARGET_LABELS = {
  local: "本地",
  cloud: "云端",
};

let runtimeConfig = null;

export function configureEnvironment(config) {
  runtimeConfig = config;
}

export function getRuntimeConfig() {
  if (!runtimeConfig) {
    throw new Error("Frontend runtime configuration has not been loaded");
  }
  return runtimeConfig;
}

export function environmentOptions() {
  return Object.keys(getRuntimeConfig().targets).map((value) => ({
    value,
    label: labelForTarget(value),
  }));
}

export function assertApiTarget(target) {
  if (!getRuntimeConfig().targets[target]) {
    throw new Error(`Unsupported API target: ${target}`);
  }
  return target;
}

export function selectedApiTarget() {
  const stored = localStorage.getItem(ENVIRONMENT_STORAGE_KEY) || "";
  return stored ? assertApiTarget(stored) : getRuntimeConfig().defaultTarget;
}

export function setSelectedApiTarget(target) {
  const nextTarget = assertApiTarget(target);
  localStorage.setItem(ENVIRONMENT_STORAGE_KEY, nextTarget);
  window.dispatchEvent(
    new CustomEvent(API_TARGET_CHANGED_EVENT, { detail: { target: nextTarget } }),
  );
}

export function endpointForTarget(target) {
  return getRuntimeConfig().targets[assertApiTarget(target)];
}

export function streamEndpointForTarget(target) {
  return endpointForTarget(target).musicWsBase;
}

function labelForTarget(target) {
  const label = TARGET_LABELS[target];
  if (!label) {
    throw new Error(`Missing display label for API target: ${target}`);
  }
  return label;
}
