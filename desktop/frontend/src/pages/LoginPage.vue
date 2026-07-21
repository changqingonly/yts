<script setup>
import { ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { ArrowRight, AtSign, Eye, EyeOff, LockKeyhole } from "@lucide/vue";
import { loginUser } from "../services/auth";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const account = ref("");
const password = ref("");
const showPassword = ref(false);
const loading = ref(false);
const error = ref("");

const showVaultUnlock = ref(auth.needsVaultUnlock);
const forceAccountLogin = ref(false);
const vaultPassphrase = ref("");
const vaultUnlocking = ref(false);
const vaultError = ref("");

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

async function submitVaultUnlock() {
  vaultUnlocking.value = true;
  vaultError.value = "";
  try {
    await auth.unlockVault(vaultPassphrase.value);
    router.push(String(route.query.redirect || "/music"));
  } catch (err) {
    vaultError.value =
      err instanceof Error && err.message === "wrong_passphrase"
        ? "密码错误，请重试"
        : err instanceof Error
          ? err.message
          : String(err);
  } finally {
    vaultUnlocking.value = false;
  }
}
</script>

<template>
  <main class="login-stage">
    <section class="login-brand" aria-label="乐兔工作室">
      <header class="brand-lockup">
        <img src="/favicon.svg" alt="" />
        <span>乐兔工作室</span>
      </header>
      <div class="brand-statement">
        <span class="brand-kicker">YOUR MUSIC, IN MOTION</span>
        <h1>让每一段灵感<br />都有地方继续生长。</h1>
        <p>创作歌词，整理作品，在同一个工作室里继续你的音乐。</p>
      </div>
      <div class="record-scene" aria-hidden="true">
        <div class="record-visual">
          <span class="record-label"><img src="/favicon.svg" alt="" /></span>
        </div>
        <div class="record-caption">
          <span>NOW PLAYING</span>
          <strong>未完成的下一首歌</strong>
          <div class="track-line"><i></i></div>
        </div>
      </div>
    </section>

    <section class="login-form-area">
      <form v-if="showVaultUnlock && !forceAccountLogin" class="login-form" @submit.prevent="submitVaultUnlock">
        <header class="form-heading">
          <span>本地已保存登录信息</span>
          <h2>输入密码解锁</h2>
          <p>系统密钥串不可用，需要你之前设置的本地密码来恢复登录。</p>
        </header>

        <label>
          <span>密码</span>
          <div class="input-shell">
            <LockKeyhole :size="17" />
            <input v-model="vaultPassphrase" autocomplete="current-password" required type="password" placeholder="输入本地密码" />
          </div>
        </label>
        <p v-if="vaultError" class="auth-error" role="alert">{{ vaultError }}</p>
        <button class="auth-primary" type="submit" :disabled="vaultUnlocking">
          <span>{{ vaultUnlocking ? "解锁中" : "解锁" }}</span>
          <ArrowRight :size="18" />
        </button>
        <p class="register-prompt">
          <button type="button" class="link-button" @click="forceAccountLogin = true">改用账号密码登录</button>
        </p>
      </form>
      <form v-else class="login-form" @submit.prevent="submitLogin">
        <header class="form-heading">
          <span>欢迎回来</span>
          <h2>登录乐兔工作室</h2>
          <p>继续上次没有写完的那首歌。</p>
        </header>

        <label>
          <span>账号</span>
          <div class="input-shell">
            <AtSign :size="17" />
            <input v-model.trim="account" autocomplete="username" required placeholder="邮箱或用户名" />
          </div>
        </label>
        <label>
          <span>密码</span>
          <div class="input-shell">
            <LockKeyhole :size="17" />
            <input
              v-model="password"
              autocomplete="current-password"
              required
              :type="showPassword ? 'text' : 'password'"
              placeholder="输入密码"
            />
            <button
              class="password-toggle"
              type="button"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" :size="17" />
              <Eye v-else :size="17" />
            </button>
          </div>
        </label>
        <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
        <button class="auth-primary" type="submit" :disabled="loading">
          <span>{{ loading ? "登录中" : "进入工作室" }}</span>
          <ArrowRight :size="18" />
        </button>
        <p class="register-prompt">第一次来？<RouterLink to="/auth/register">创建账号</RouterLink></p>
      </form>
      <footer>乐兔工作室 · 专注你的音乐创作</footer>
    </section>
  </main>
</template>

<style scoped>
.login-stage {
  background: #06111f;
  display: grid;
  grid-template-columns: minmax(0, 1.18fr) minmax(420px, 0.82fr);
  min-height: 100vh;
  overflow: hidden;
}

.login-brand {
  background: #0a1b2b;
  border-right: 1px solid #19364a;
  display: grid;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
  overflow: hidden;
  padding: clamp(30px, 4vw, 64px);
  position: relative;
}

.brand-lockup {
  align-items: center;
  display: flex;
  gap: 11px;
}

.brand-lockup img {
  height: 30px;
  width: 30px;
}

.brand-lockup span {
  color: #edf6f4;
  font-size: 14px;
  font-weight: 750;
}

.brand-statement {
  align-self: center;
  max-width: 650px;
  padding-bottom: 8vh;
  position: relative;
  z-index: 1;
}

.brand-kicker,
.record-caption > span,
.form-heading > span {
  color: #4fd1bd;
  font-size: 10px;
  font-weight: 800;
}

.brand-statement h1 {
  color: #f1f0e9;
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: clamp(34px, 4vw, 58px);
  font-weight: 600;
  line-height: 1.3;
  margin: 18px 0;
}

.brand-statement p {
  color: #8fa9b9;
  font-size: 14px;
  line-height: 1.8;
  margin: 0;
  max-width: 470px;
}

.record-scene {
  align-items: end;
  bottom: clamp(30px, 4vw, 64px);
  display: grid;
  gap: 22px;
  grid-template-columns: 126px minmax(0, 230px);
  position: absolute;
  right: clamp(30px, 5vw, 80px);
}

.record-visual {
  background: #10151a;
  border: 1px solid #30404a;
  border-radius: 50%;
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.32);
  height: 126px;
  position: relative;
  width: 126px;
}

.record-visual::before,
.record-visual::after {
  border: 1px solid rgba(143, 169, 185, 0.18);
  border-radius: 50%;
  content: "";
  inset: 14px;
  position: absolute;
}

.record-visual::after {
  inset: 25px;
}

.record-label {
  align-items: center;
  background: #d95f5f;
  border-radius: 50%;
  display: flex;
  height: 48px;
  inset: 50%;
  justify-content: center;
  position: absolute;
  transform: translate(-50%, -50%);
  width: 48px;
  z-index: 1;
}

.record-label img {
  height: 23px;
  width: 23px;
}

.record-caption {
  display: grid;
  gap: 7px;
  padding-bottom: 8px;
}

.record-caption strong {
  color: #d8e7e5;
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: 14px;
}

.track-line {
  background: #1b3948;
  height: 2px;
  margin-top: 6px;
  width: 100%;
}

.track-line i {
  background: #4fd1bd;
  display: block;
  height: 2px;
  width: 38%;
}

.login-form-area {
  align-items: center;
  background: #071426;
  display: grid;
  grid-template-rows: 1fr auto;
  min-width: 0;
  padding: clamp(32px, 6vw, 96px);
}

.login-form {
  display: grid;
  gap: 19px;
  margin: auto;
  max-width: 410px;
  width: 100%;
}

.form-heading {
  margin-bottom: 17px;
}

.form-heading h2 {
  color: #edf6ff;
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: 30px;
  font-weight: 600;
  margin: 9px 0 7px;
}

.form-heading p,
.register-prompt,
.login-form-area > footer {
  color: #7890a5;
  font-size: 12px;
  margin: 0;
}

.login-form label {
  display: grid;
  gap: 8px;
}

.login-form label > span {
  color: #a9bfce;
  font-size: 12px;
  font-weight: 700;
}

.input-shell {
  align-items: center;
  border-bottom: 1px solid #27506b;
  color: #64869c;
  display: grid;
  gap: 10px;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  min-height: 50px;
}

.input-shell:focus-within {
  border-color: #4fd1bd;
  color: #4fd1bd;
}

.input-shell input {
  background: transparent;
  border: 0;
  color: #edf6ff;
  font: inherit;
  min-height: 49px;
  outline: 0;
  padding: 0;
}

.input-shell input::placeholder {
  color: #526e82;
}

.password-toggle {
  background: transparent;
  border: 0;
  color: #7890a5;
  cursor: pointer;
  display: inline-flex;
  padding: 8px;
}

.auth-primary {
  align-items: center;
  background: #20b8a3;
  border: 0;
  border-radius: 6px;
  color: #031b19;
  cursor: pointer;
  display: flex;
  font: inherit;
  font-weight: 750;
  justify-content: space-between;
  margin-top: 7px;
  min-height: 48px;
  padding: 0 17px;
}

.auth-primary:hover:not(:disabled) {
  background: #4fd1bd;
}

.auth-primary:disabled {
  cursor: wait;
  opacity: 0.65;
}

.register-prompt {
  text-align: center;
}

.register-prompt a,
.link-button {
  color: #4fd1bd;
  font-weight: 700;
  text-decoration: none;
}

.link-button {
  background: transparent;
  border: 0;
  cursor: pointer;
  font: inherit;
  padding: 0;
}

.auth-error {
  border-left: 2px solid #fb7185;
  color: #fda4af;
  font-size: 12px;
  margin: 0;
  padding: 8px 11px;
}

.login-form-area > footer {
  justify-self: center;
  padding-top: 32px;
}

@media (max-width: 860px) {
  .login-stage {
    grid-template-columns: minmax(0, 1fr);
  }

  .login-brand {
    min-height: 230px;
    padding: 28px;
  }

  .brand-statement {
    align-self: end;
    padding: 42px 0 0;
  }

  .brand-statement h1 {
    font-size: 30px;
    margin: 12px 0 0;
  }

  .brand-statement p,
  .record-scene {
    display: none;
  }

  .login-form-area {
    padding: 46px 28px 28px;
  }
}

@media (max-width: 460px) {
  .login-brand {
    min-height: 190px;
  }

  .brand-statement h1 {
    font-size: 25px;
  }

  .login-form-area {
    align-items: start;
    padding-top: 36px;
  }
}
</style>
