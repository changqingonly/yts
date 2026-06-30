import { requestJson } from "./http";

export function listSongs(limit = 100) {
  return requestJson(`/api/song/list?limit=${limit}`);
}

export function getSong(songId) {
  return requestJson(`/api/song/${songId}`);
}

export function saveSong(payload) {
  return requestJson("/api/song/save", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSong(songId, payload) {
  return requestJson(`/api/song/${songId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteSong(songId) {
  return requestJson(`/api/song/${songId}`, { method: "DELETE" });
}
