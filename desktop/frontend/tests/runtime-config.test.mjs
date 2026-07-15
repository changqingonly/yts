import assert from "node:assert/strict";
import test from "node:test";

import { validateRuntimeConfig } from "../src/services/runtimeConfig.js";

const VALID_RUNTIME_CONFIG = {
  schemaVersion: 1,
  profile: "local",
  defaultTarget: "local",
  targets: {
    local: {
      apiBase: "http://127.0.0.1:8765",
      musicWsBase: "ws://127.0.0.1:8799",
    },
    cloud: {
      apiBase: "http://127.0.0.1:8000",
      musicWsBase: "ws://127.0.0.1:8000",
    },
  },
};

function runtimeConfig(overrides = {}) {
  return {
    ...JSON.parse(JSON.stringify(VALID_RUNTIME_CONFIG)),
    ...overrides,
  };
}

test("validateRuntimeConfig accepts the strict runtime document", () => {
  assert.deepEqual(validateRuntimeConfig(runtimeConfig()), VALID_RUNTIME_CONFIG);
});

test("validateRuntimeConfig rejects missing required targets", () => {
  const config = runtimeConfig();
  delete config.targets.cloud;

  assert.throws(() => validateRuntimeConfig(config), /missing required target: cloud/i);
});

test("validateRuntimeConfig rejects unknown top-level keys", () => {
  const config = runtimeConfig({ unexpected: true });

  assert.throws(() => validateRuntimeConfig(config), /unsupported runtime config key: unexpected/i);
});

test("validateRuntimeConfig rejects invalid URL schemes", () => {
  const config = runtimeConfig();
  config.targets.local.apiBase = "ftp://127.0.0.1:8765";

  assert.throws(() => validateRuntimeConfig(config), /targets.local.apiBase must use http or https/i);
});

test("validateRuntimeConfig rejects secret-shaped keys anywhere in the document", () => {
  const config = runtimeConfig();
  config.targets.local.jwtSecret = "must-not-be-here";

  assert.throws(() => validateRuntimeConfig(config), /secret-shaped runtime config key/i);
});

test("validateRuntimeConfig rejects default targets outside targets", () => {
  const config = runtimeConfig({ defaultTarget: "missing" });

  assert.throws(() => validateRuntimeConfig(config), /defaultTarget must reference a configured target/i);
});
