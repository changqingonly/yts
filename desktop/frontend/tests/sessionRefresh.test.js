import assert from "node:assert/strict";
import test from "node:test";

import { createSessionRefresher } from "../src/services/sessionRefresh.js";

test("concurrent refresh calls share one request", async () => {
  let calls = 0;
  let resolve;
  const pending = new Promise((done) => { resolve = done; });
  const refresher = createSessionRefresher({ refresh: async () => { calls += 1; return pending; } });
  const first = refresher.refreshNow();
  const second = refresher.refreshNow();
  resolve({ access_token: "token", expires_at: 1000 });
  assert.deepEqual(await first, await second);
  assert.equal(calls, 1);
});

test("network failure does not invoke invalid-session callback", async () => {
  let invalidated = false;
  const refresher = createSessionRefresher({
    refresh: async () => { throw Object.assign(new Error("offline"), { code: "NETWORK" }); },
    onInvalid: () => { invalidated = true; },
  });
  await assert.rejects(refresher.refreshNow(), /offline/);
  assert.equal(invalidated, false);
});

test("explicit unauthorized refresh invalidates the session", async () => {
  let invalidated = false;
  const refresher = createSessionRefresher({
    refresh: async () => { throw Object.assign(new Error("revoked"), { status: 401 }); },
    onInvalid: () => { invalidated = true; },
  });
  await assert.rejects(refresher.refreshNow(), /revoked/);
  assert.equal(invalidated, true);
});
