const DEFAULT_BASES = {
  local: "http://127.0.0.1:8765",
  cloud: "http://127.0.0.1:8000",
};

export function apiBase(target = localStorage.getItem("yts-target") || "local") {
  return DEFAULT_BASES[target] ?? DEFAULT_BASES.local;
}

export async function requestJson(path, options = {}) {
  const token = localStorage.getItem("yts-access-token") || "";
  const headers = {
    "Content-Type": "application/json",
    ...(token && options.auth !== false ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers ?? {}),
  };
  const response = await fetch(`${apiBase()}${path}`, {
    ...options,
    headers,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && options.auth !== false) {
      localStorage.removeItem("yts-access-token");
      localStorage.removeItem("yts-user");
      window.dispatchEvent(new CustomEvent("yts-auth-expired", { detail: { path, body } }));
    }
    const detail = body?.detail ?? body?.message ?? `${response.status} ${response.statusText}`;
    const error = new Error(detail);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}
