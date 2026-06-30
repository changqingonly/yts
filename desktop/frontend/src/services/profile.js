import { requestJson } from "./http";

export function fetchProfile() {
  return requestJson("/api/user/profile");
}

export function updateProfile(payload) {
  return requestJson("/api/user/profile", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function uploadAvatar(imageDataUrl) {
  return requestJson("/api/user/avatar/upload", {
    method: "POST",
    body: JSON.stringify({ image_data_url: imageDataUrl }),
  });
}
