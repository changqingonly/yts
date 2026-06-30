<script setup>
import { ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { LogIn } from "@lucide/vue";
import { loginUser } from "../services/auth";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const account = ref("");
const password = ref("");
const loading = ref(false);
const error = ref("");

async function submitLogin() {
  loading.value = true;
  error.value = "";
  try {
    const session = await loginUser({ account: account.value, password: password.value });
    auth.setSession(session);
    router.push(String(route.query.redirect || "/music"));
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="auth-page">
    <form class="auth-panel" @submit.prevent="submitLogin">
      <div class="auth-heading">
        <span><LogIn :size="18" /></span>
        <div>
          <h1>登录深海工作室</h1>
          <p>继续管理你的音乐、创作与资产。</p>
        </div>
      </div>
      <label>
        <span>账号</span>
        <input v-model.trim="account" autocomplete="username" required placeholder="邮箱或用户名" />
      </label>
      <label>
        <span>密码</span>
        <input v-model="password" autocomplete="current-password" required type="password" />
      </label>
      <p v-if="error" class="auth-error">{{ error }}</p>
      <button class="auth-primary" type="submit" :disabled="loading">
        {{ loading ? "登录中" : "登录" }}
      </button>
      <RouterLink class="auth-link" to="/auth/register">没有账号？去注册</RouterLink>
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
  max-width: 420px;
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
