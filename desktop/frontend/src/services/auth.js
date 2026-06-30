import { requestJson } from "./http";

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
  const key = await requestJson("/api/auth/register_key", { auth: false });
  const publicKey = await importRsaOaepPublicKey(key.jwk);
  return requestJson("/api/auth/register", {
    method: "POST",
    auth: false,
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
  const key = await requestJson("/api/auth/login_key", { auth: false });
  const publicKey = await importRsaOaepPublicKey(key.jwk);
  return requestJson("/api/auth/login", {
    method: "POST",
    auth: false,
    body: JSON.stringify({
      account,
      key_id: key.key_id,
      password_ciphertext_b64: await encryptWithKey(publicKey, password),
    }),
  });
}

export function fetchCurrentUser() {
  return requestJson("/api/auth/me");
}

export function logoutUser() {
  return requestJson("/api/auth/logout", { method: "POST" });
}
