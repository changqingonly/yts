import { startSidecar } from "./desktop";
import { healthCheck } from "./transport";

const startupByTarget = new Map();

export function resetLocalPlaybackStartup() {
  for (const [target, entry] of startupByTarget) {
    if (entry.status !== "starting") {
      startupByTarget.delete(target);
    }
  }
}

export function startLocalPlayback({
  target = "local",
  timeoutMs = 5000,
  prepare,
  startSidecar: startSidecarCallback = startSidecar,
  healthCheck: healthCheckCallback = healthCheck,
} = {}) {
  if (typeof prepare !== "function") {
    throw new Error("startLocalPlayback requires prepare callback");
  }
  if (startupByTarget.has(target)) {
    return startupByTarget.get(target).promise;
  }

  const entry = { status: "starting", promise: null };
  entry.promise = startLocalPlaybackReadiness({
    target,
    timeoutMs,
    prepare,
    startSidecarCallback,
    healthCheckCallback,
  }).then(
    (result) => {
      entry.status = "ready";
      return result;
    },
    (error) => {
      entry.status = error.stage === "timeout" ? "timeout" : "failed";
      throw error;
    },
  );
  startupByTarget.set(target, entry);
  return entry.promise;
}

async function startLocalPlaybackReadiness({
  target,
  timeoutMs,
  prepare,
  startSidecarCallback,
  healthCheckCallback,
}) {
  const readinessPromise = (async () => {
    await runStage("sidecar", () => startSidecarCallback());
    await runStage("health", () => healthCheckCallback(target));
    await runStage("prepare", () => prepare({ target }));
    return { status: "ready", target };
  })();
  let timeoutId;
  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(createStartupTimeoutError(timeoutMs)), timeoutMs);
  });
  try {
    return await Promise.race([readinessPromise, timeoutPromise]);
  } finally {
    clearTimeout(timeoutId);
  }
}

async function runStage(stage, callback) {
  try {
    return await callback();
  } catch (error) {
    if (error instanceof Error) {
      error.stage = stage;
      throw error;
    }
    const startupError = new Error(String(error));
    startupError.stage = stage;
    throw startupError;
  }
}

function createStartupTimeoutError(timeoutMs) {
  const error = new Error(`Local playback startup timed out after ${timeoutMs}ms`);
  error.stage = "timeout";
  return error;
}
