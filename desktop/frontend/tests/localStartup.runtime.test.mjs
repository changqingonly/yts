import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { resetLocalPlaybackStartup, startLocalApiReadiness, startLocalPlayback } from "../src/services/localStartup.js";

afterEach(() => {
  resetLocalPlaybackStartup();
});

test("shares one playback Promise and runs API readiness before preparation", async () => {
  const events = [];
  const options = {
    target: "runtime-shared-playback",
    timeoutMs: 50,
    startSidecar: async () => events.push("sidecar"),
    healthCheck: async (target) => events.push(`health:${target}`),
    prepare: async ({ target }) => events.push(`prepare:${target}`),
  };

  const first = startLocalPlayback(options);
  const second = startLocalPlayback({
    ...options,
    prepare: async () => events.push("unexpected-preparation"),
  });

  assert.strictEqual(first, second);
  assert.deepEqual(await first, { status: "ready", target: "runtime-shared-playback" });
  assert.deepEqual(events, [
    "sidecar",
    "health:runtime-shared-playback",
    "prepare:runtime-shared-playback",
  ]);
});

test("shares local API readiness without reporting playback ready", async () => {
  const events = [];
  const options = {
    target: "runtime-api-readiness",
    timeoutMs: 50,
    startSidecar: async () => events.push("sidecar"),
    healthCheck: async (target) => events.push(`health:${target}`),
  };

  const apiReadiness = startLocalApiReadiness(options);
  const playback = startLocalPlayback({
    ...options,
    prepare: async ({ target }) => events.push(`prepare:${target}`),
  });

  assert.deepEqual(await apiReadiness, { status: "online", target: "runtime-api-readiness" });
  assert.deepEqual(await playback, { status: "ready", target: "runtime-api-readiness" });
  assert.deepEqual(events, [
    "sidecar",
    "health:runtime-api-readiness",
    "prepare:runtime-api-readiness",
  ]);
});

test("propagates the original stage error", async () => {
  const originalError = new Error("health unavailable");

  await assert.rejects(
    startLocalPlayback({
      target: "runtime-stage-error",
      timeoutMs: 50,
      startSidecar: async () => {},
      healthCheck: async () => {
        throw originalError;
      },
      prepare: async () => {},
    }),
    (error) => error === originalError && error.stage === "health",
  );
});

test("timeout and reset retain in-flight ownership until readiness settles", async () => {
  let releaseSidecar;
  let sidecarCalls = 0;
  const waitForSidecar = new Promise((resolve) => {
    releaseSidecar = resolve;
  });
  const options = {
    target: "runtime-timeout-reset",
    timeoutMs: 10,
    startSidecar: async () => {
      sidecarCalls += 1;
      await waitForSidecar;
    },
    healthCheck: async () => {},
    prepare: async () => {},
  };

  const timedOut = startLocalPlayback(options);
  await assert.rejects(timedOut, (error) => error.stage === "timeout");
  resetLocalPlaybackStartup();
  const continuedWait = startLocalPlayback({ ...options, timeoutMs: 50 });
  assert.notStrictEqual(continuedWait, timedOut);
  assert.equal(sidecarCalls, 1);

  releaseSidecar();
  await continuedWait;
  resetLocalPlaybackStartup();

  const retried = startLocalPlayback(options);
  assert.notStrictEqual(retried, timedOut);
  await retried;
  assert.equal(sidecarCalls, 2);
});

test("retry after timeout waits on the same underlying readiness", async () => {
  resetLocalPlaybackStartup();
  let releasePrepare;
  let prepareCalls = 0;
  const prepareGate = new Promise((resolve) => {
    releasePrepare = resolve;
  });
  const options = {
    target: "retry-timeout",
    timeoutMs: 5,
    startSidecar: async () => {},
    healthCheck: async () => {},
    prepare: async () => {
      prepareCalls += 1;
      await prepareGate;
    },
  };

  await assert.rejects(startLocalPlayback(options), (error) => error.stage === "timeout");
  resetLocalPlaybackStartup();
  const retry = startLocalPlayback({ ...options, timeoutMs: 50 });
  releasePrepare();

  assert.deepEqual(await retry, { status: "ready", target: "retry-timeout" });
  assert.equal(prepareCalls, 1);
});
