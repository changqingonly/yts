import { requestJson } from "./http";
import { uploadForm } from "./transport";

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
  const form = new FormData();
  form.append("file", file, filename || file.name || "audio.bin");
  if (mime) form.append("mime", mime);
  if (filename) form.append("filename", filename);
  return uploadForm("/api/music/local_import/upload", form);
}
