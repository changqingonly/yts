<script setup>
import { ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { UserPlus } from "@lucide/vue";
import { registerUser } from "../services/auth";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const email = ref("");
const password = ref("");
const confirmPassword = ref("");
const agreementAccepted = ref(false);
const loading = ref(false);
const error = ref("");

async function submitRegister() {
  loading.value = true;
  error.value = "";
  try {
    const session = await registerUser({
      email: email.value,
      password: password.value,
      confirmPassword: confirmPassword.value,
      agreementAccepted: agreementAccepted.value,
    });
    auth.setSession(session);
    router.push("/profile/setup");
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="auth-page">
    <form class="auth-panel" @submit.prevent="submitRegister">
      <div class="auth-heading">
        <span><UserPlus :size="18" /></span>
        <div>
          <h1>注册深海工作室</h1>
          <p>创建账号后可同步资产、积分和播放器列表。</p>
        </div>
      </div>
      <label>
        <span>邮箱</span>
        <input v-model.trim="email" autocomplete="email" required type="email" />
      </label>
      <label>
        <span>密码</span>
        <input v-model="password" autocomplete="new-password" required type="password" />
      </label>
      <label>
        <span>确认密码</span>
        <input v-model="confirmPassword" autocomplete="new-password" required type="password" />
      </label>
      <label class="agreement-row">
        <input v-model="agreementAccepted" required type="checkbox" />
        <span>同意用户协议和隐私条款</span>
      </label>
      <p v-if="error" class="auth-error">{{ error }}</p>
      <button class="auth-primary" type="submit" :disabled="loading">
        {{ loading ? "注册中" : "注册" }}
      </button>
      <RouterLink class="auth-link" to="/auth/login">已有账号？去登录</RouterLink>
    </form>
  </main>
</template>

<style scoped>
.auth-page {
  align-items: center;
  background: var(--color-bg);
  display: grid;
  min-height: 100vh;
  padding: 24px;
  place-items: center;
}

.auth-panel {
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: var(--shadow-panel);
  display: grid;
  gap: 14px;
  max-width: 460px;
  padding: 24px;
  width: 100%;
}

.auth-heading {
  align-items: center;
  display: flex;
  gap: 12px;
}

.auth-heading > span {
  align-items: center;
  background: var(--color-accent-soft);
  border-radius: 8px;
  color: var(--color-accent);
  display: inline-flex;
  height: 40px;
  justify-content: center;
  width: 40px;
}

h1 {
  font-size: 22px;
  margin: 0;
}

p {
  color: var(--color-muted);
  margin: 3px 0 0;
}

label {
  display: grid;
  gap: 6px;
}

label span {
  color: var(--color-muted-strong);
  font-size: 13px;
  font-weight: 700;
}

input {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text);
  font: inherit;
  min-height: 42px;
  padding: 0 12px;
}

.agreement-row {
  align-items: center;
  display: flex;
}

.agreement-row input {
  min-height: 0;
}

.auth-primary {
  background: var(--color-accent-strong);
  border: 0;
  border-radius: 8px;
  color: var(--color-heading);
  font: inherit;
  font-weight: 800;
  min-height: 42px;
}

.auth-link {
  color: var(--color-accent);
  font-weight: 700;
  text-align: center;
  text-decoration: none;
}

.auth-error {
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  border-radius: 8px;
  color: var(--color-danger);
  padding: 9px 10px;
}
</style>
