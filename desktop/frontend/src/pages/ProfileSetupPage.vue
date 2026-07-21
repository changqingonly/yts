<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { Camera, ChartNoAxesColumnIncreasing, Save, SlidersHorizontal, UserRound } from "@lucide/vue";
import { fetchProfile, updateProfile, uploadAvatar } from "../services/profile";
import { apiResourceUrl } from "../services/transport";
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
const profileLoading = ref(true);
const profileReady = ref(false);
const avatarUploading = ref(false);

const actionsDisabled = computed(
  () => !profileReady.value || loading.value || profileLoading.value || avatarUploading.value,
);
const avatarPreviewUrl = computed(() => (avatarUrl.value ? apiResourceUrl(avatarUrl.value) : ""));

async function loadProfile() {
  error.value = "";
  profileLoading.value = true;
  profileReady.value = false;
  try {
    const profile = await fetchProfile();
    username.value = profile.username || "";
    gender.value = profile.gender || "unknown";
    birthday.value = profile.birthday || "";
    bio.value = profile.bio || "";
    avatarUrl.value = profile.avatar_url || "";
    auth.setUser({ ...(auth.user || {}), ...profile });
    profileReady.value = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    profileLoading.value = false;
  }
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

  message.value = "";
  error.value = "";
  avatarUploading.value = true;
  try {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    const result = await uploadAvatar(dataUrl);
    avatarUrl.value = result.avatar_url;
    message.value = "头像已更新，保存资料后生效";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    avatarUploading.value = false;
    event.target.value = "";
  }
}

onMounted(loadProfile);
</script>

<template>
  <section class="profile-page">
    <header class="profile-header">
      <div>
        <p class="profile-eyebrow">工作台偏好</p>
        <h1>个人资料</h1>
      </div>
      <button
        class="save-button"
        type="submit"
        form="profile-form"
        :disabled="actionsDisabled"
      >
        <Save :size="16" />
        {{ loading ? "保存中" : "保存更改" }}
      </button>
    </header>

    <p v-if="profileLoading" class="loading-message" role="status">正在加载个人资料</p>
    <p v-if="message" class="ok-message" role="status">{{ message }}</p>
    <p v-if="error" class="error-message" role="alert">{{ error }}</p>

    <div class="profile-shell">
      <nav class="settings-nav" aria-label="设置分类">
        <RouterLink class="settings-nav-item" to="/settings">
          <SlidersHorizontal :size="17" />
          <span>通用</span>
        </RouterLink>
        <RouterLink
          class="settings-nav-item"
          :to="{ path: '/settings', query: { section: 'usage' } }"
        >
          <ChartNoAxesColumnIncreasing :size="17" />
          <span>用量</span>
        </RouterLink>
        <RouterLink class="settings-nav-item active" to="/profile/setup" aria-current="page">
          <UserRound :size="17" />
          <span>账户</span>
        </RouterLink>
      </nav>

      <main class="profile-content">
        <div class="section-heading">
          <p>账户</p>
          <h2>头像与公开信息</h2>
          <span>这些信息用于工作台中的个人身份展示。</span>
        </div>

        <form id="profile-form" class="profile-form" @submit.prevent="saveProfile">
          <section class="avatar-section">
            <div class="avatar-preview">
              <img v-if="avatarPreviewUrl" :src="avatarPreviewUrl" alt="当前头像" />
              <span v-else>{{ (username || auth.displayName).slice(0, 1).toUpperCase() }}</span>
            </div>
            <div class="avatar-copy">
              <strong>{{ username || auth.displayName }}</strong>
              <small>支持常见图片格式，上传后可立即预览。</small>
            </div>
            <label :class="['upload-button', { disabled: actionsDisabled }]">
              <Camera :size="16" />
              {{ avatarUploading ? "上传中" : "更换头像" }}
              <input
                accept="image/*"
                type="file"
                :disabled="actionsDisabled"
                aria-label="选择新头像"
                @change="onAvatarChange"
              />
            </label>
          </section>

          <section class="form-section">
            <div class="form-section-heading">
              <h3>基本信息</h3>
              <p>昵称会显示在你的创作记录和个人资料中。</p>
            </div>
            <div class="field-grid">
              <label class="field">
                <span>昵称</span>
                <input v-model.trim="username" required :disabled="actionsDisabled" />
              </label>
              <label class="field">
                <span>性别</span>
                <select v-model="gender" :disabled="actionsDisabled">
                  <option value="unknown">不透露</option>
                  <option value="female">女</option>
                  <option value="male">男</option>
                  <option value="other">其他</option>
                </select>
              </label>
              <label class="field birthday-field">
                <span>生日</span>
                <input v-model="birthday" type="date" :disabled="actionsDisabled" />
              </label>
            </div>
          </section>

          <section class="form-section biography-section">
            <div class="form-section-heading">
              <h3>个人简介</h3>
              <p>简要描述你的创作偏好或音乐身份。</p>
            </div>
            <label class="field">
              <span class="visually-hidden">简介</span>
              <textarea
                v-model="bio"
                rows="6"
                :disabled="actionsDisabled"
                placeholder="写下你的创作偏好或音乐身份"
              ></textarea>
            </label>
          </section>
        </form>
      </main>
    </div>
  </section>
</template>

<style scoped>
.profile-page {
  align-content: start;
  display: grid;
  gap: 24px;
  margin: 0 auto;
  max-width: 1060px;
  min-height: 100%;
  padding: 40px 44px 64px;
  width: 100%;
}

.profile-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.profile-eyebrow,
.section-heading > p {
  color: var(--color-accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  margin: 0 0 6px;
  text-transform: uppercase;
}

h1,
h2,
h3,
p {
  margin-top: 0;
}

h1 {
  color: var(--color-heading);
  font-size: 28px;
  line-height: 1.15;
  margin-bottom: 0;
}

.save-button,
.upload-button {
  align-items: center;
  border-radius: 7px;
  display: inline-flex;
  font: inherit;
  font-size: 13px;
  font-weight: 750;
  gap: 8px;
  justify-content: center;
  min-height: 38px;
  padding: 0 13px;
}

.save-button {
  background: var(--color-accent-strong);
  border: 1px solid var(--color-accent-strong);
  color: var(--color-heading);
  cursor: pointer;
}

.save-button:hover:not(:disabled) {
  background: var(--color-accent);
  border-color: var(--color-accent);
}

.save-button:disabled,
.upload-button.disabled {
  cursor: wait;
  opacity: 0.62;
}

.profile-shell {
  align-items: start;
  display: grid;
  gap: 40px;
  grid-template-columns: 168px minmax(0, 1fr);
}

.settings-nav {
  border-right: 1px solid var(--color-border-soft);
  display: grid;
  gap: 4px;
  padding-right: 16px;
}

.settings-nav-item {
  align-items: center;
  border-radius: 6px;
  color: var(--color-muted);
  display: flex;
  font-size: 13px;
  font-weight: 700;
  gap: 10px;
  min-height: 40px;
  padding: 0 11px;
  position: relative;
  text-decoration: none;
}

.settings-nav-item::before {
  background: transparent;
  border-radius: 2px;
  content: "";
  height: 18px;
  left: -17px;
  position: absolute;
  width: 2px;
}

.settings-nav-item:hover {
  color: var(--color-heading);
}

.settings-nav-item.active {
  background: var(--color-accent-soft);
  color: var(--color-heading);
}

.settings-nav-item.active::before {
  background: var(--color-accent);
}

.profile-content {
  min-width: 0;
}

.section-heading {
  border-bottom: 1px solid var(--color-border-soft);
  padding-bottom: 22px;
}

.section-heading h2 {
  color: var(--color-heading);
  font-size: 20px;
  line-height: 1.25;
  margin-bottom: 7px;
}

.section-heading > span {
  color: var(--color-muted);
  font-size: 13px;
}

.profile-form {
  display: grid;
}

.avatar-section {
  align-items: center;
  border-bottom: 1px solid var(--color-border-soft);
  display: flex;
  gap: 14px;
  min-height: 112px;
  padding: 20px 0;
}

.avatar-preview {
  align-items: center;
  background: var(--color-accent-soft);
  border: 1px solid var(--color-border);
  border-radius: 50%;
  color: var(--color-accent);
  display: inline-flex;
  flex: 0 0 auto;
  font-size: 24px;
  font-weight: 800;
  height: 72px;
  justify-content: center;
  overflow: hidden;
  width: 72px;
}

.avatar-preview img {
  height: 100%;
  object-fit: cover;
  width: 100%;
}

.avatar-copy {
  display: grid;
  flex: 1;
  gap: 5px;
  min-width: 0;
}

.avatar-copy strong {
  color: var(--color-text);
  font-size: 14px;
  overflow-wrap: anywhere;
}

.avatar-copy small,
.form-section-heading p {
  color: var(--color-muted);
  font-size: 12px;
  margin-bottom: 0;
}

.upload-button {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-muted-strong);
  cursor: pointer;
  flex: 0 0 auto;
}

.upload-button:hover:not(.disabled) {
  border-color: var(--color-muted);
  color: var(--color-heading);
}

.upload-button input {
  height: 1px;
  opacity: 0;
  overflow: hidden;
  position: absolute;
  width: 1px;
}

.form-section {
  border-bottom: 1px solid var(--color-border-soft);
  display: grid;
  gap: 18px;
  padding: 24px 0;
}

.form-section-heading h3 {
  color: var(--color-muted-strong);
  font-size: 13px;
  margin-bottom: 5px;
}

.field-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.field {
  display: grid;
  gap: 7px;
}

.field > span:not(.visually-hidden) {
  color: var(--color-muted-strong);
  font-size: 12px;
  font-weight: 700;
}

.birthday-field {
  grid-column: 1 / 2;
}

input,
select,
textarea {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 7px;
  color: var(--color-text);
  font: inherit;
  font-size: 13px;
  min-height: 40px;
  padding: 9px 11px;
  width: 100%;
}

textarea {
  line-height: 1.55;
  min-height: 126px;
  resize: vertical;
}

input:disabled,
select:disabled,
textarea:disabled {
  cursor: wait;
  opacity: 0.62;
}

.biography-section {
  border-bottom: 0;
}

.loading-message,
.ok-message,
.error-message {
  border-radius: 7px;
  margin: 0;
  padding: 11px 13px;
}

.loading-message {
  background: var(--color-panel-soft);
  border: 1px solid var(--color-border-soft);
  color: var(--color-muted-strong);
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

.visually-hidden {
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  height: 1px;
  overflow: hidden;
  position: absolute;
  white-space: nowrap;
  width: 1px;
}

.settings-nav-item:focus-visible,
.save-button:focus-visible,
.upload-button:focus-within,
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

@media (max-width: 720px) {
  .profile-page {
    gap: 20px;
    padding: 28px 20px 48px;
  }

  .profile-shell {
    gap: 28px;
    grid-template-columns: 1fr;
  }

  .settings-nav {
    border-bottom: 1px solid var(--color-border-soft);
    border-right: 0;
    display: flex;
    gap: 4px;
    overflow-x: auto;
    padding: 0 0 10px;
  }

  .settings-nav-item {
    flex: 1 0 94px;
    justify-content: center;
    min-height: 38px;
    padding: 0 10px;
  }

  .settings-nav-item::before {
    bottom: -11px;
    height: 2px;
    left: 20%;
    top: auto;
    width: 60%;
  }
}

@media (max-width: 460px) {
  .profile-header {
    align-items: flex-start;
    gap: 16px;
  }

  .save-button {
    padding: 0;
    width: 40px;
  }

  .save-button {
    font-size: 0;
  }

  .save-button svg {
    height: 16px;
    width: 16px;
  }

  .avatar-section {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .avatar-copy {
    min-width: calc(100% - 86px);
  }

  .upload-button {
    margin-left: 86px;
    width: calc(100% - 86px);
  }

  .field-grid {
    grid-template-columns: 1fr;
  }

  .birthday-field {
    grid-column: auto;
  }
}
</style>
