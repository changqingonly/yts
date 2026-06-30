import { apiBase, requestJson } from "./http";

export function syncPlaylist({ since = 0, limit = 500, uploads = [] } = {}) {
  const params = new URLSearchParams();
  params.set("since", String(since));
  params.set("limit", String(limit));
  return requestJson(`/api/music/playlist/sync?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify({ uploads }),
  });
}

export async function uploadLocalImport({ file, mime, filename } = {}) {
  if (!file) {
    throw new Error("uploadLocalImport requires file");
  }
  const token = localStorage.getItem("yts-access-token") || "";
  const form = new FormData();
  form.append("file", file, filename || file.name || "audio.bin");
  if (mime) form.append("mime", mime);
  if (filename) form.append("filename", filename);
  const response = await fetch(`${apiBase()}/api/music/local_import/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || `本地音频上传失败 (${response.status})`);
  }
  return payload;
}
