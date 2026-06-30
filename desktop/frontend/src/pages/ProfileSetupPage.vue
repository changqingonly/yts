<script setup>
import { onMounted, ref } from "vue";
import { Camera, Save } from "@lucide/vue";
import { fetchProfile, updateProfile, uploadAvatar } from "../services/profile";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const username = ref("");
const gender = ref("unknown");
const birthday = ref("");
const bio = ref("");
const avatarUrl = ref("");
const message = ref("");
const error = ref("");
const loading = ref(false);

async function loadProfile() {
  const profile = await fetchProfile();
  username.value = profile.username || "";
  gender.value = profile.gender || "unknown";
  birthday.value = profile.birthday || "";
  bio.value = profile.bio || "";
  avatarUrl.value = profile.avatar_url || "";
  auth.setUser({ ...(auth.user || {}), ...profile });
}

async function saveProfile() {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    const profile = await updateProfile({
      username: username.value,
      avatar_url: avatarUrl.value || null,
      birthday: birthday.value || null,
      bio: bio.value,
      gender: gender.value,
    });
    auth.setUser({ ...(auth.user || {}), ...profile });
    message.value = "资料已保存";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function onAvatarChange(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  const result = await uploadAvatar(dataUrl);
  avatarUrl.value = result.avatar_url;
}

onMounted(loadProfile);
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p>用户相关</p>
        <h1>个人设置</h1>
      </div>
      <button class="primary-action" type="button" :disabled="loading" @click="saveProfile">
        <Save :size="16" />
        保存
      </button>
    </header>

    <section class="settings-grid">
      <div class="avatar-card">
        <div class="avatar-preview">
          <img v-if="avatarUrl" :src="avatarUrl" alt="头像" />
          <span v-else>{{ (username || auth.displayName).slice(0, 1).toUpperCase() }}</span>
        </div>
        <label class="upload-button">
          <Camera :size="15" />
          头像
          <input accept="image/*" type="file" @change="onAvatarChange" />
        </label>
      </div>

      <form class="profile-form" @submit.prevent="saveProfile">
        <label>
          <span>昵称</span>
          <input v-model.trim="username" required />
        </label>
        <label>
          <span>性别</span>
          <select v-model="gender">
            <option value="unknown">不透露</option>
            <option value="female">女</option>
            <option value="male">男</option>
            <option value="other">其他</option>
          </select>
        </label>
        <label>
          <span>生日</span>
          <input v-model="birthday" type="date" />
        </label>
        <label class="wide">
          <span>简介</span>
          <textarea v-model="bio" rows="6" placeholder="写下你的创作偏好或音乐身份"></textarea>
        </label>
      </form>
    </section>

    <p v-if="message" class="ok-message">{{ message }}</p>
    <p v-if="error" class="error-message">{{ error }}</p>
  </section>
</template>

<style scoped>
.page {
  display: grid;
  gap: 16px;
  padding: 24px;
}

.page-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.page-header p {
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 700;
  margin: 0 0 4px;
}

h1 {
  font-size: 26px;
  margin: 0;
}

.primary-action,
.upload-button {
  align-items: center;
  border-radius: 8px;
  display: inline-flex;
  font-weight: 800;
  gap: 8px;
  justify-content: center;
}

.primary-action {
  background: var(--color-accent-strong);
  border: 0;
  color: var(--color-heading);
  min-height: 38px;
  padding: 0 16px;
}

.settings-grid {
  align-items: start;
  display: grid;
  gap: 16px;
  grid-template-columns: 220px minmax(0, 1fr);
}

.avatar-card,
.profile-form {
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
}

.avatar-card {
  display: grid;
  gap: 12px;
  justify-items: center;
}

.avatar-preview {
  align-items: center;
  background: var(--color-accent-soft);
  border-radius: 50%;
  color: var(--color-accent);
  display: inline-flex;
  font-size: 34px;
  font-weight: 900;
  height: 120px;
  justify-content: center;
  overflow: hidden;
  width: 120px;
}

.avatar-preview img {
  height: 100%;
  object-fit: cover;
  width: 100%;
}

.upload-button {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  min-height: 34px;
  padding: 0 12px;
}

.upload-button input {
  display: none;
}

.profile-form {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

label {
  display: grid;
  gap: 6px;
}

label.wide {
  grid-column: 1 / -1;
}

label span {
  color: var(--color-muted-strong);
  font-size: 13px;
  font-weight: 800;
}

input,
select,
textarea {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text);
  font: inherit;
  padding: 9px 11px;
}

textarea {
  resize: vertical;
}

.ok-message,
.error-message {
  border-radius: 8px;
  margin: 0;
  padding: 10px 12px;
}

.ok-message {
  background: var(--color-success-soft);
  border: 1px solid var(--color-success);
  color: var(--color-success);
}

.error-message {
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
}
</style>
