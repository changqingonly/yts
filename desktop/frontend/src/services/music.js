import { requestJson } from "./http";
import { requestBlob, uploadForm } from "./transport";

export function syncPlaylist({ since = 0, limit = 500, uploads = [] } = {}) {
  const params = new URLSearchParams();
  params.set("since", String(since));
  params.set("limit", String(limit));
  return requestJson(`/api/music/playlist/sync?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify({ uploads }),
  });
}

export function listPlaylists({ scope } = {}) {
  const params = new URLSearchParams();
  if (scope) params.set("scope", scope);
  const query = params.toString();
  return requestJson(`/api/music/playlists${query ? `?${query}` : ""}`);
}

export function ensureDefaultPlaylist({ scope = "cloud" } = {}) {
  return requestJson("/api/music/playlists/default", {
    method: "POST",
    body: JSON.stringify({ scope }),
  });
}

export function createPlaylist({ name, scope = "cloud" } = {}) {
  return requestJson("/api/music/playlists", {
    method: "POST",
    body: JSON.stringify({ name, scope }),
  });
}

export function listPlaylistItems({ playlistId: rawPlaylistId } = {}) {
  if (!rawPlaylistId) throw new Error("listPlaylistItems requires playlistId");
  const playlistId = encodeURIComponent(rawPlaylistId);
  return requestJson(`/api/music/playlists/${playlistId}/items`);
}

export function listDeletedPlaylistItems({ playlistId: rawPlaylistId } = {}) {
  if (!rawPlaylistId) throw new Error("listDeletedPlaylistItems requires playlistId");
  const playlistId = encodeURIComponent(rawPlaylistId);
  return requestJson(`/api/music/playlists/${playlistId}/items/deleted`);
}

export function appendPlaylistItems({ playlistId: rawPlaylistId, items } = {}) {
  if (!rawPlaylistId) throw new Error("appendPlaylistItems requires playlistId");
  const playlistId = encodeURIComponent(rawPlaylistId);
  return requestJson(`/api/music/playlists/${playlistId}/items`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export function deletePlaylistItem({ playlistId: rawPlaylistId, itemId: rawItemId } = {}) {
  if (!rawPlaylistId) throw new Error("deletePlaylistItem requires playlistId");
  if (!rawItemId) throw new Error("deletePlaylistItem requires itemId");
  const playlistId = encodeURIComponent(rawPlaylistId);
  const itemId = encodeURIComponent(rawItemId);
  return requestJson(`/api/music/playlists/${playlistId}/items/${itemId}`, {
    method: "DELETE",
  });
}

export function restorePlaylistItem({ playlistId: rawPlaylistId, itemId: rawItemId } = {}) {
  if (!rawPlaylistId) throw new Error("restorePlaylistItem requires playlistId");
  if (!rawItemId) throw new Error("restorePlaylistItem requires itemId");
  const playlistId = encodeURIComponent(rawPlaylistId);
  const itemId = encodeURIComponent(rawItemId);
  return requestJson(`/api/music/playlists/${playlistId}/items/${itemId}/restore`, {
    method: "POST",
  });
}

export function reorderPlaylistItems({ playlistId: rawPlaylistId, orderedItemIds } = {}) {
  if (!rawPlaylistId) throw new Error("reorderPlaylistItems requires playlistId");
  const playlistId = encodeURIComponent(rawPlaylistId);
  return requestJson(`/api/music/playlists/${playlistId}/items/reorder`, {
    method: "POST",
    body: JSON.stringify({ ordered_item_ids: orderedItemIds }),
  });
}

export async function loadSongObjectUrl({ contentHash: rawContentHash, target } = {}) {
  if (!rawContentHash) throw new Error("loadSongObjectUrl requires contentHash");
  const contentHash = encodeURIComponent(rawContentHash);
  const blob = await requestBlob(`/api/music/file/${contentHash}`, { target });
  return URL.createObjectURL(blob);
}

export async function uploadSong({ file, mime, filename } = {}) {
  if (!file) {
    throw new Error("uploadSong requires file");
  }
  const form = new FormData();
  form.append("file", file, filename || file.name || "audio.bin");
  if (mime) form.append("mime", mime);
  if (filename) form.append("filename", filename);
  return uploadForm("/api/music/upload", form);
}
