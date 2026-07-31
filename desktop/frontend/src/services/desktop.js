import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { isTauriRuntime } from "./environment";

const MODEL_DOWNLOAD_PROGRESS_EVENT = "model-download-progress";

function requireTauri() {
  if (!isTauriRuntime()) {
    throw new Error("This feature is only available in the desktop app.");
  }
}

export function checkLocalModels() {
  requireTauri();
  return invoke("check_local_models");
}

export function downloadLocalModels(artifactOrigin) {
  requireTauri();
  return invoke("download_local_models", { artifactOrigin });
}

export function startGateway() {
  requireTauri();
  return invoke("start_gateway");
}

export function stopGateway() {
  requireTauri();
  return invoke("stop_gateway");
}

export function restartGateway() {
  requireTauri();
  return invoke("restart_gateway");
}

export function startSidecar() {
  requireTauri();
  return invoke("start_sidecar");
}

export function stopSidecar() {
  requireTauri();
  return invoke("stop_sidecar");
}

/** acestep.cpp(音乐生成)上游无预编译产物,需源码构建;独立于文本/图片两档。 */
export function checkAcestep() {
  requireTauri();
  return invoke("check_acestep");
}

export function buildAcestep() {
  requireTauri();
  return invoke("build_acestep");
}

/** handler(progress) 在每次下载进度事件触发时调用;返回值为取消订阅函数。 */
export async function onModelDownloadProgress(handler) {
  requireTauri();
  const unlisten = await listen(MODEL_DOWNLOAD_PROGRESS_EVENT, (event) => handler(event.payload));
  return unlisten;
}

/** 以下为桌面端登录持久化:Keychain 优先,不可用时前端显式报错(不做静默兜底),
 * 用户可选改用密码保护的本地保险库(vault_*)。 */
export function keychainLoad() {
  requireTauri();
  return invoke("keychain_load");
}

export function keychainStore(deviceId, refreshToken) {
  requireTauri();
  return invoke("keychain_store", { deviceId, refreshToken });
}

export function keychainClear() {
  requireTauri();
  return invoke("keychain_clear");
}

export function vaultExists() {
  requireTauri();
  return invoke("vault_exists");
}

export function vaultStore(passphrase, deviceId, refreshToken) {
  requireTauri();
  return invoke("vault_store", { passphrase, deviceId, refreshToken });
}

export function vaultUnlock(passphrase) {
  requireTauri();
  return invoke("vault_unlock", { passphrase });
}

export function vaultClear() {
  requireTauri();
  return invoke("vault_clear");
}
