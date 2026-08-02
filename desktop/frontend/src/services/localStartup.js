const apiReadinessByTarget = new Map();
const playbackByTarget = new Map();

export function resetLocalPlaybackStartup() {
  clearSettledEntries(apiReadinessByTarget);
  clearSettledEntries(playbackByTarget);
}

export function startLocalApiReadiness({
  target = "local",
  timeoutMs = 5000,
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
  timeoutMs = 5000,
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

  const entry = createEntry();
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
    await runStage("health", () => healthCheckCallback(target));
    return { status: "online", target };
  })();
  trackEntrySettlement(entry);
  apiReadinessByTarget.set(target, entry);
  return entry;
}

function createEntry() {
  return { status: "starting", readinessPromise: null, promise: null };
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
    timeoutId = setTimeout(() => reject(createStartupTimeoutError(timeoutMs)), timeoutMs);
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
