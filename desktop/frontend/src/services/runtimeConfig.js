import { configureEnvironment } from "./environment.js";

const DEFAULT_RUNTIME_CONFIG_URL = "/runtime-config.json";
const TOP_LEVEL_KEYS = new Set(["schemaVersion", "profile", "defaultTarget", "targets"]);
const REQUIRED_TARGETS = ["local", "cloud"];
const TARGET_KEYS = new Set(["apiBase", "musicWsBase"]);
const SECRET_KEY_PATTERN = /(secret|token|key|dsn|password|credential)/i;

export async function loadRuntimeConfig(url = runtimeConfigUrl()) {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(
      `Failed to load frontend runtime config ${url}: ${response.status} ${response.statusText}`,
    );
  }
  const config = validateRuntimeConfig(await response.json());
  configureEnvironment(config);
  return config;
}

export function runtimeConfigUrl() {
  const viteEnv = import.meta.env ?? {};
  return viteEnv.VITE_YTS_RUNTIME_CONFIG_URL || DEFAULT_RUNTIME_CONFIG_URL;
}

export function validateRuntimeConfig(value) {
  assertPlainObject(value, "runtime config");
  rejectSecretKeys(value, []);
  assertAllowedKeys(Object.keys(value), TOP_LEVEL_KEYS, "runtime config");
  if (value.schemaVersion !== 1) {
    throw new Error("runtime config schemaVersion must be 1");
  }
  assertNonEmptyString(value.profile, "profile");
  assertNonEmptyString(value.defaultTarget, "defaultTarget");
  assertPlainObject(value.targets, "targets");

  for (const target of REQUIRED_TARGETS) {
    if (!Object.hasOwn(value.targets, target)) {
      throw new Error(`missing required target: ${target}`);
    }
  }
  const targetNames = Object.keys(value.targets);
  for (const target of targetNames) {
    if (!REQUIRED_TARGETS.includes(target)) {
      throw new Error(`unsupported runtime target: ${target}`);
    }
    validateTarget(target, value.targets[target]);
  }
  if (!Object.hasOwn(value.targets, value.defaultTarget)) {
    throw new Error("defaultTarget must reference a configured target");
  }
  return {
    schemaVersion: 1,
    profile: value.profile,
    defaultTarget: value.defaultTarget,
    targets: Object.fromEntries(
      REQUIRED_TARGETS.map((target) => [
        target,
        {
          apiBase: value.targets[target].apiBase,
          musicWsBase: value.targets[target].musicWsBase,
        },
      ]),
    ),
  };
}

function validateTarget(target, value) {
  assertPlainObject(value, `targets.${target}`);
  assertAllowedKeys(Object.keys(value), TARGET_KEYS, `targets.${target}`);
  assertUrlScheme(value.apiBase, `targets.${target}.apiBase`, ["http:", "https:"]);
  assertUrlScheme(value.musicWsBase, `targets.${target}.musicWsBase`, ["ws:", "wss:"]);
}

function assertPlainObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
}

function assertAllowedKeys(keys, allowedKeys, label) {
  for (const key of keys) {
    if (!allowedKeys.has(key)) {
      throw new Error(`unsupported runtime config key: ${key} at ${label}`);
    }
  }
}

function assertNonEmptyString(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
}

function assertUrlScheme(value, label, protocols) {
  assertNonEmptyString(value, label);
  let parsed;
  try {
    parsed = new URL(value);
  } catch (error) {
    throw new Error(`${label} must be a valid URL`, { cause: error });
  }
  if (!protocols.includes(parsed.protocol)) {
    const readableSchemes = protocols.map((protocol) => protocol.replace(":", "")).join(" or ");
    throw new Error(`${label} must use ${readableSchemes}`);
  }
}

function rejectSecretKeys(value, path) {
  if (!value || typeof value !== "object") {
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    const nextPath = [...path, key];
    if (SECRET_KEY_PATTERN.test(key)) {
      throw new Error(`secret-shaped runtime config key: ${nextPath.join(".")}`);
    }
    rejectSecretKeys(child, nextPath);
  }
}
