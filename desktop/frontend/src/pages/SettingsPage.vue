<script setup>
import { onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { Coins, LogOut, SlidersHorizontal, UserRound } from "@lucide/vue";
import { fetchCreditBalance, fetchCreditLedger, fetchDailyUsage } from "../services/credits";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const balance = ref(null);
const ledger = ref([]);
const dailyUsage = ref(null);
const modelProvider = ref(localStorage.getItem("yts-model-provider") || "local");
const error = ref("");
const loggingOut = ref(false);

async function loadSettings() {
  error.value = "";
  try {
    balance.value = await fetchCreditBalance();
    ledger.value = await fetchCreditLedger();
    dailyUsage.value = await fetchDailyUsage();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function saveModelPreference() {
  localStorage.setItem("yts-model-provider", modelProvider.value);
}

async function logout() {
  error.value = "";
  loggingOut.value = true;
  try {
    await auth.logoutAction();
    router.push({ name: "login" });
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loggingOut.value = false;
  }
}

onMounted(loadSettings);
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p>系统设置</p>
        <h1>设置</h1>
      </div>
      <div class="settings-actions">
        <RouterLink class="profile-link" to="/profile/setup"><UserRound :size="16" /> 个人设置</RouterLink>
        <button class="logout-button" type="button" :disabled="loggingOut" @click="logout">
          <LogOut :size="16" />
          {{ loggingOut ? "退出中" : "退出登录" }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-message">{{ error }}</p>

    <section class="settings-layout">
      <article class="panel">
        <div class="panel-title">
          <Coins :size="17" />
          <h2>积分流水</h2>
        </div>
        <div class="balance-line">
          <strong>{{ balance?.balance ?? "--" }}</strong>
          <span>当前积分</span>
        </div>
        <ul class="ledger-list">
          <li v-for="row in ledger" :key="row.id">
            <span>{{ row.kind }} · {{ row.biz_type }}</span>
            <strong>{{ row.change_amount > 0 ? "+" : "" }}{{ row.change_amount }}</strong>
          </li>
          <li v-if="!ledger.length" class="empty-row">暂无流水</li>
        </ul>
      </article>

      <article class="panel">
        <div class="panel-title">
          <SlidersHorizontal :size="17" />
          <h2>每日额度</h2>
        </div>
        <div class="quota-grid">
          <div>
            <span>歌词生成</span>
            <strong>{{ dailyUsage?.lyrics?.used ?? 0 }}/{{ dailyUsage?.lyrics?.limit ?? 100 }}</strong>
          </div>
          <div>
            <span>图片生成</span>
            <strong>{{ dailyUsage?.images?.used ?? 0 }}/{{ dailyUsage?.images?.limit ?? 100 }}</strong>
          </div>
          <div>
            <span>音频特效</span>
            <strong>{{ dailyUsage?.audio_effects?.used ?? 0 }}/{{ dailyUsage?.audio_effects?.limit ?? 100 }}</strong>
          </div>
        </div>
      </article>

      <article class="panel wide">
        <div class="panel-title">
          <SlidersHorizontal :size="17" />
          <h2>模型偏好</h2>
        </div>
        <label class="preference-row">
          <span>默认模型通道</span>
          <select v-model="modelProvider" @change="saveModelPreference">
            <option value="local">本地</option>
            <option value="cloud">云端</option>
          </select>
        </label>
      </article>
    </section>
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

h1,
h2 {
  margin: 0;
}

h1 {
  font-size: 26px;
}

h2 {
  font-size: 15px;
}

.settings-actions {
  align-items: center;
  display: flex;
  gap: 10px;
}

.profile-link,
.logout-button {
  align-items: center;
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text);
  display: inline-flex;
  font-weight: 800;
  gap: 8px;
  min-height: 36px;
  padding: 0 12px;
  text-decoration: none;
}

.logout-button {
  cursor: pointer;
  font: inherit;
}

.logout-button:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.logout-button:disabled {
  cursor: wait;
  opacity: 0.62;
}

.settings-layout {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.panel {
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  display: grid;
  gap: 14px;
  padding: 16px;
}

.panel.wide {
  grid-column: 1 / -1;
}

.panel-title {
  align-items: center;
  color: var(--color-muted-strong);
  display: flex;
  gap: 8px;
}

.balance-line {
  align-items: end;
  display: flex;
  gap: 10px;
}

.balance-line strong {
  font-size: 34px;
}

.balance-line span,
.quota-grid span {
  color: var(--color-muted);
  font-size: 13px;
}

.ledger-list {
  display: grid;
  gap: 8px;
  list-style: none;
  margin: 0;
  padding: 0;
}

.ledger-list li,
.quota-grid div,
.preference-row {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  padding: 10px;
}

.ledger-list li {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.empty-row {
  color: var(--color-muted);
}

.quota-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.quota-grid div {
  display: grid;
  gap: 6px;
}

.quota-grid strong {
  font-size: 20px;
}

.preference-row {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

select {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text);
  font: inherit;
  min-height: 36px;
  padding: 0 10px;
}

.error-message {
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  border-radius: 8px;
  color: var(--color-danger);
  margin: 0;
  padding: 10px 12px;
}
</style>
