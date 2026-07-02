export const API_TARGET_CHANGED_EVENT = "yts-target-changed";
export const ENVIRONMENT_STORAGE_KEY = "yts-target";
export const DEFAULT_ENVIRONMENT_TARGET = "cloud";

export const ENVIRONMENT_TARGETS = {
  local: { label: "本地", apiBase: "http://127.0.0.1:8765", musicWsBase: "ws://127.0.0.1:8799" },
  cloud: { label: "云端", apiBase: "http://127.0.0.1:8000", musicWsBase: "ws://127.0.0.1:8000" },
};

export function environmentOptions() {
  return Object.entries(ENVIRONMENT_TARGETS).map(([value, endpoint]) => ({
    value,
    label: endpoint.label,
  }));
}

export function assertApiTarget(target) {
  if (!ENVIRONMENT_TARGETS[target]) {
    throw new Error(`Unsupported API target: ${target}`);
  }
  return target;
}

export function selectedApiTarget() {
  const stored = localStorage.getItem(ENVIRONMENT_STORAGE_KEY) || "";
  return stored ? assertApiTarget(stored) : DEFAULT_ENVIRONMENT_TARGET;
}

export function setSelectedApiTarget(target) {
  const nextTarget = assertApiTarget(target);
  localStorage.setItem(ENVIRONMENT_STORAGE_KEY, nextTarget);
  window.dispatchEvent(new CustomEvent(API_TARGET_CHANGED_EVENT, { detail: { target: nextTarget } }));
}

export function endpointForTarget(target) {
  return ENVIRONMENT_TARGETS[assertApiTarget(target)];
}

export function streamEndpointForTarget(target) {
  return endpointForTarget(target).musicWsBase;
}
