<script setup>
import { ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { ArrowRight, AtSign, Eye, EyeOff, LockKeyhole } from "@lucide/vue";
import { registerUser } from "../services/auth";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const email = ref("");
const password = ref("");
const confirmPassword = ref("");
const showPassword = ref(false);
const showConfirmPassword = ref(false);
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
  <main class="register-stage">
    <section class="register-brand" aria-label="乐兔工作室">
      <header class="brand-lockup">
        <img src="/favicon.svg" alt="" />
        <span>乐兔工作室</span>
      </header>
      <div class="brand-statement">
        <span class="brand-kicker">START YOUR STUDIO</span>
        <h1>从第一句歌词开始，<br />建立你的作品世界。</h1>
        <p>保存每次灵感，整理每首作品，让创作慢慢长成自己的声音。</p>
      </div>
      <div class="record-scene" aria-hidden="true">
        <div class="record-visual">
          <span class="record-label"><img src="/favicon.svg" alt="" /></span>
        </div>
        <div class="record-caption">
          <span>NEW SESSION</span>
          <strong>你的第一首作品</strong>
          <div class="track-line"><i></i></div>
        </div>
      </div>
    </section>

    <section class="register-form-area">
      <form class="register-form" @submit.prevent="submitRegister">
        <header class="form-heading">
          <span>创建工作室</span>
          <h2>注册乐兔工作室</h2>
          <p>一个账号，同步你的创作与音乐资产。</p>
        </header>

        <label>
          <span>邮箱</span>
          <div class="input-shell">
            <AtSign :size="17" />
            <input v-model.trim="email" autocomplete="email" required type="email" placeholder="name@example.com" />
          </div>
        </label>
        <label>
          <span>密码</span>
          <div class="input-shell">
            <LockKeyhole :size="17" />
            <input
              v-model="password"
              autocomplete="new-password"
              required
              :type="showPassword ? 'text' : 'password'"
              placeholder="设置密码"
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
        <label>
          <span>确认密码</span>
          <div class="input-shell">
            <LockKeyhole :size="17" />
            <input
              v-model="confirmPassword"
              autocomplete="new-password"
              required
              :type="showConfirmPassword ? 'text' : 'password'"
              placeholder="再次输入密码"
            />
            <button
              class="password-toggle"
              type="button"
              :aria-label="showConfirmPassword ? '隐藏确认密码' : '显示确认密码'"
              @click="showConfirmPassword = !showConfirmPassword"
            >
              <EyeOff v-if="showConfirmPassword" :size="17" />
              <Eye v-else :size="17" />
            </button>
          </div>
        </label>

        <label class="agreement-row">
          <input v-model="agreementAccepted" required type="checkbox" />
          <span>我已阅读并同意用户协议和隐私条款</span>
        </label>
        <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
        <button class="auth-primary" type="submit" :disabled="loading">
          <span>{{ loading ? "注册中" : "创建账号" }}</span>
          <ArrowRight :size="18" />
        </button>
        <p class="login-prompt">已经有账号？<RouterLink to="/auth/login">返回登录</RouterLink></p>
      </form>
      <footer>乐兔工作室 · 专注你的音乐创作</footer>
    </section>
  </main>
</template>

<style scoped>
.register-stage {
  background: #06111f;
  display: grid;
  grid-template-columns: minmax(0, 1.18fr) minmax(420px, 0.82fr);
  min-height: 100vh;
  overflow: hidden;
}

.register-brand {
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
  max-width: 680px;
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
  max-width: 480px;
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
  width: 18%;
}

.register-form-area {
  align-items: center;
  background: #071426;
  display: grid;
  grid-template-rows: 1fr auto;
  min-width: 0;
  padding: clamp(28px, 5vw, 80px);
}

.register-form {
  display: grid;
  gap: 15px;
  margin: auto;
  max-width: 410px;
  width: 100%;
}

.form-heading {
  margin-bottom: 8px;
}

.form-heading h2 {
  color: #edf6ff;
  font-family: "Songti SC", "Noto Serif SC", Georgia, serif;
  font-size: 28px;
  font-weight: 600;
  margin: 8px 0 6px;
}

.form-heading p,
.login-prompt,
.register-form-area > footer {
  color: #7890a5;
  font-size: 12px;
  margin: 0;
}

.register-form > label:not(.agreement-row) {
  display: grid;
  gap: 7px;
}

.register-form > label:not(.agreement-row) > span {
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
  min-height: 46px;
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
  min-height: 45px;
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

.agreement-row {
  align-items: center;
  color: #8fa9b9;
  cursor: pointer;
  display: flex;
  font-size: 11px;
  gap: 9px;
  margin-top: 3px;
}

.agreement-row input {
  accent-color: #20b8a3;
  height: 16px;
  margin: 0;
  width: 16px;
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
  margin-top: 3px;
  min-height: 46px;
  padding: 0 17px;
}

.auth-primary:hover:not(:disabled) {
  background: #4fd1bd;
}

.auth-primary:disabled {
  cursor: wait;
  opacity: 0.65;
}

.login-prompt {
  text-align: center;
}

.login-prompt a {
  color: #4fd1bd;
  font-weight: 700;
  text-decoration: none;
}

.auth-error {
  border-left: 2px solid #fb7185;
  color: #fda4af;
  font-size: 12px;
  margin: 0;
  padding: 8px 11px;
}

.register-form-area > footer {
  justify-self: center;
  padding-top: 24px;
}

@media (max-width: 860px) {
  .register-stage {
    grid-template-columns: minmax(0, 1fr);
  }

  .register-brand {
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

  .register-form-area {
    padding: 40px 28px 26px;
  }
}

@media (max-width: 460px) {
  .register-brand {
    min-height: 180px;
  }

  .brand-statement h1 {
    font-size: 24px;
  }

  .register-form-area {
    align-items: start;
    padding-top: 32px;
  }
}
</style>
