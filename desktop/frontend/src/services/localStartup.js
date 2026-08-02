const apiReadinessByTarget = new Map();
const playbackByTarget = new Map();
const HEALTH_RETRY_INTERVAL_MS = 100;
export const LOCAL_STARTUP_TIMEOUT_MS = 30000;

export function resetLocalPlaybackStartup() {
  clearSettledEntries(apiReadinessByTarget);
  clearSettledEntries(playbackByTarget);
}

export function startLocalApiReadiness({
  target = "local",
  timeoutMs = LOCAL_STARTUP_TIMEOUT_MS,
  startSidecar,
  healthCheck,
} = {}) {
  const entry = getLocalApiReadinessEntry({ target, startSidecar, healthCheck });
  if (!entry.promise) {
    attachBoundedWait(entry, timeoutMs);
  }
  return entry.promise;
}

export function startLocalPlayback({
  target = "local",
  timeoutMs = LOCAL_STARTUP_TIMEOUT_MS,
  prepare,
  startSidecar,
  healthCheck,
} = {}) {
  const prepareCallback = requireCallback("prepare", prepare);
  const apiEntry = getLocalApiReadinessEntry({ target, startSidecar, healthCheck });
  if (playbackByTarget.has(target)) {
    const existingEntry = playbackByTarget.get(target);
    if (!existingEntry.promise) attachBoundedWait(existingEntry, timeoutMs);
    return existingEntry.promise;
  }

  const entry = createEntry(apiEntry);
  entry.readinessPromise = (async () => {
    await apiEntry.readinessPromise;
    await runStage("prepare", () => prepareCallback({ target }));
    return { status: "ready", target };
  })();
  trackEntrySettlement(entry);
  attachBoundedWait(entry, timeoutMs);
  playbackByTarget.set(target, entry);
  return entry.promise;
}

function attachBoundedWait(entry, timeoutMs) {
  const boundedPromise = raceReadinessTimeout(entry, timeoutMs);
  entry.promise = boundedPromise;
  boundedPromise.then(
    () => {},
    (error) => {
      if (
        error?.stage === "timeout"
        && entry.status === "starting"
        && entry.promise === boundedPromise
      ) {
        entry.promise = null;
      }
    },
  );
}

function getLocalApiReadinessEntry({ target, startSidecar, healthCheck }) {
  if (apiReadinessByTarget.has(target)) {
    return apiReadinessByTarget.get(target);
  }

  const startSidecarCallback = requireCallback("startSidecar", startSidecar);
  const healthCheckCallback = requireCallback("healthCheck", healthCheck);
  const entry = createEntry();
  entry.readinessPromise = (async () => {
    await runStage("sidecar", () => startSidecarCallback());
    await waitForHealth({ target, healthCheckCallback, entry });
    return { status: "online", target };
  })();
  trackEntrySettlement(entry);
  apiReadinessByTarget.set(target, entry);
  return entry;
}

async function waitForHealth({ target, healthCheckCallback, entry }) {
  for (;;) {
    try {
      return await runStage("health", () => healthCheckCallback(target));
    } catch (error) {
      entry.lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, HEALTH_RETRY_INTERVAL_MS));
  }
}

function createEntry(errorSource = null) {
  return {
    status: "starting",
    readinessPromise: null,
    promise: null,
    lastError: null,
    errorSource,
  };
}

function trackEntrySettlement(entry) {
  entry.readinessPromise.then(
    () => {
      entry.status = "ready";
    },
    () => {
      entry.status = "failed";
    },
  );
}

function raceReadinessTimeout(entry, timeoutMs) {
  let timeoutId;
  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      const error = createStartupTimeoutError(timeoutMs);
      error.cause = entry.lastError || entry.errorSource?.lastError || null;
      reject(error);
    }, timeoutMs);
  });
  return Promise.race([entry.readinessPromise, timeoutPromise]).finally(() => {
    clearTimeout(timeoutId);
  });
}

function clearSettledEntries(entries) {
  for (const [target, entry] of entries) {
    if (entry.status === "starting") continue;
    entries.delete(target);
  }
}

function requireCallback(name, callback) {
  if (typeof callback !== "function") {
    throw new Error(`local startup requires ${name} callback`);
  }
  return callback;
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
