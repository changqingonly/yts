import { requestJsonOverHttp } from "./transport";

// 账号体系(注册/登录/密码校验/刷新/登出)只走云端 profile,和"本地/云端"生成目标切换解耦——
// 生成目标只控制推理请求打到哪个后端,不影响账号在哪验证。见 docs/superpowers 相关设计记录。
const AUTH_TARGET = "cloud";

function base64Std(bytes) {
  let binary = "";
  for (let index = 0; index < bytes.byteLength; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return btoa(binary);
}

async function importRsaOaepPublicKey(jwk) {
  return crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  );
}

async function encryptWithKey(publicKey, plaintext) {
  const encoded = new TextEncoder().encode(plaintext);
  const ciphertext = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, publicKey, encoded);
  return base64Std(new Uint8Array(ciphertext));
}

export async function registerUser({ email, password, confirmPassword, agreementAccepted }) {
  const key = await requestJsonOverHttp("/api/auth/register_key", { auth: false, target: AUTH_TARGET });
  const publicKey = await importRsaOaepPublicKey(key.jwk);
  return requestJsonOverHttp("/api/auth/register", {
    method: "POST",
    auth: false,
    target: AUTH_TARGET,
    body: JSON.stringify({
      email,
      key_id: key.key_id,
      password_ciphertext_b64: await encryptWithKey(publicKey, password),
      confirm_password_ciphertext_b64: await encryptWithKey(publicKey, confirmPassword),
      agreement_accepted: agreementAccepted,
    }),
  });
}

export async function loginUser({ account, password }) {
  const key = await requestJsonOverHttp("/api/auth/login_key", { auth: false, target: AUTH_TARGET });
  const publicKey = await importRsaOaepPublicKey(key.jwk);
  return requestJsonOverHttp("/api/auth/login", {
    method: "POST",
    auth: false,
    target: AUTH_TARGET,
    body: JSON.stringify({
      account,
      key_id: key.key_id,
      password_ciphertext_b64: await encryptWithKey(publicKey, password),
    }),
  });
}

export function fetchCurrentUser() {
  return requestJsonOverHttp("/api/auth/me", { target: AUTH_TARGET });
}

export function refreshCurrentSession({ deviceId, refreshToken } = {}) {
  return requestJsonOverHttp("/api/auth/refresh", {
    method: "POST",
    auth: false,
    target: AUTH_TARGET,
    headers: { "X-Refresh-Request-ID": crypto.randomUUID() },
    body:
      deviceId && refreshToken
        ? JSON.stringify({ device_id: deviceId, refresh_token: refreshToken })
        : undefined,
  });
}

export function logoutUser() {
  return requestJsonOverHttp("/api/auth/logout", { method: "POST", target: AUTH_TARGET });
}
