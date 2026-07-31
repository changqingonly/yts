<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  ChartNoAxesColumnIncreasing,
  ChevronRight,
  Coins,
  Download,
  KeyRound,
  LogOut,
  SlidersHorizontal,
  UserRound,
} from "@lucide/vue";
import { fetchCreditBalance, fetchCreditLedger, fetchDailyUsage } from "../services/credits";
import { isTauriRuntime } from "../services/environment";
import { apiBase } from "../services/http";
import {
  buildAcestep,
  checkAcestep,
  checkLocalModels,
  downloadLocalModels,
  onModelDownloadProgress,
  restartGateway,
} from "../services/desktop";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const balance = ref(null);
const ledger = ref([]);
const dailyUsage = ref(null);
const modelProvider = ref(localStorage.getItem("yts-model-provider") || "local");
const error = ref("");
const navigationError = ref("");
const loggingOut = ref(false);
const activeSection = ref("general");
const vaultPassphrase = ref("");
const vaultConfirmPassphrase = ref("");
const vaultError = ref("");
const savingVault = ref(false);

const showDesktopSection = isTauriRuntime();
const settingsSections = [
  { key: "general", label: "通用", icon: SlidersHorizontal },
  { key: "usage", label: "用量", icon: ChartNoAxesColumnIncreasing },
  ...(showDesktopSection ? [{ key: "desktop", label: "本地模型", icon: Download }] : []),
  { key: "account", label: "账户", icon: UserRound },
];

const localModels = ref(null);
const localModelsError = ref("");
const downloading = ref(false);
const downloadProgress = ref(null);
let unlistenDownloadProgress = null;

const localModelRows = computed(() => {
  if (!localModels.value) return [];
  return [
    { key: "llama_binary", label: "llama.cpp(文本推理二进制)", ready: localModels.value.llama_binary },
    { key: "llama_model", label: "文本模型权重(Qwen2.5-7B-Instruct)", ready: localModels.value.llama_model },
    { key: "sd_binary", label: "stable-diffusion.cpp(图片推理二进制)", ready: localModels.value.sd_binary },
    { key: "sd_model", label: "图片模型权重(FLUX.1-schnell)", ready: localModels.value.sd_model },
  ];
});

async function refreshLocalModels() {
  if (!showDesktopSection) return;
  try {
    localModels.value = await checkLocalModels();
  } catch (err) {
    localModelsError.value = err instanceof Error ? err.message : String(err);
  }
}

async function startModelDownload() {
  if (downloading.value) return;
  downloading.value = true;
  localModelsError.value = "";
  downloadProgress.value = null;
  try {
    localModels.value = await downloadLocalModels(apiBase("cloud"));
    await restartGateway();
  } catch (err) {
    localModelsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    downloading.value = false;
  }
}

// acestep.cpp(音乐生成)上游无预编译产物,需源码构建,独立于上面的文本/图片下载。
const acestep = ref(null);
const acestepError = ref("");
const buildingAcestep = ref(false);

async function refreshAcestep() {
  if (!showDesktopSection) return;
  try {
    acestep.value = await checkAcestep();
  } catch (err) {
    acestepError.value = err instanceof Error ? err.message : String(err);
  }
}

async function startAcestepBuild() {
  if (buildingAcestep.value) return;
  buildingAcestep.value = true;
  acestepError.value = "";
  downloadProgress.value = null;
  try {
    acestep.value = await buildAcestep();
    await restartGateway();
  } catch (err) {
    acestepError.value = err instanceof Error ? err.message : String(err);
  } finally {
    buildingAcestep.value = false;
  }
}

function sectionFromQuery(value) {
  if (value === undefined) return "general";
  if (typeof value === "string" && settingsSections.some((section) => section.key === value)) {
    return value;
  }
  throw new Error(`未知设置分类: ${String(value)}`);
}

function openSection(section) {
  const query = section === "general" ? {} : { section };
  router.push({ path: "/settings", query });
}

const usageRows = computed(() =>
  [
    {
      key: "lyrics",
      label: "歌词生成",
      used: dailyUsage.value?.lyrics?.used ?? 0,
      limit: dailyUsage.value?.lyrics?.limit ?? 100,
    },
    {
      key: "images",
      label: "图片生成",
      used: dailyUsage.value?.images?.used ?? 0,
      limit: dailyUsage.value?.images?.limit ?? 100,
    },
    {
      key: "audio_effects",
      label: "音频特效",
      used: dailyUsage.value?.audio_effects?.used ?? 0,
      limit: dailyUsage.value?.audio_effects?.limit ?? 100,
    },
  ].map((row) => ({
    ...row,
    percent: Math.min(100, Math.max(0, (row.used / row.limit) * 100)),
  })),
);

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

async function saveVaultPassphrase() {
  vaultError.value = "";
  if (!vaultPassphrase.value || vaultPassphrase.value !== vaultConfirmPassphrase.value) {
    vaultError.value = "两次输入的密码不一致";
    return;
  }
  savingVault.value = true;
  try {
    await auth.enableVaultPersistence(vaultPassphrase.value);
    vaultPassphrase.value = "";
    vaultConfirmPassphrase.value = "";
  } catch (err) {
    vaultError.value = err instanceof Error ? err.message : String(err);
  } finally {
    savingVault.value = false;
  }
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

onMounted(async () => {
  loadSettings();
  if (showDesktopSection) {
    refreshLocalModels();
    refreshAcestep();
    unlistenDownloadProgress = await onModelDownloadProgress((progress) => {
      downloadProgress.value = progress;
    });
  }
});

onUnmounted(() => {
  unlistenDownloadProgress?.();
});

watch(
  () => route.query.section,
  (section) => {
    navigationError.value = "";
    try {
      activeSection.value = sectionFromQuery(section);
    } catch (err) {
      navigationError.value = err instanceof Error ? err.message : String(err);
    }
  },
  { immediate: true },
);
</script>

<template>
  <section class="settings-page">
    <header class="settings-header">
      <div>
        <p class="settings-eyebrow">工作台偏好</p>
        <h1>设置</h1>
      </div>
    </header>

    <p v-if="navigationError || error" class="error-message" role="alert">
      {{ navigationError || error }}
    </p>

    <div class="settings-shell">
      <nav class="settings-nav" aria-label="设置分类">
        <button
          v-for="item in settingsSections"
          :key="item.key"
          :class="['settings-nav-item', { active: activeSection === item.key }]"
          :aria-current="activeSection === item.key ? 'page' : undefined"
          type="button"
          @click="openSection(item.key)"
        >
          <component :is="item.icon" :size="17" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <main class="settings-content">
        <section v-if="activeSection === 'general'" class="settings-section">
          <div class="section-heading">
            <p>通用</p>
            <h2>生成偏好</h2>
            <span>设置创作时默认使用的模型通道。</span>
          </div>

          <label class="setting-row" for="model-provider">
            <span class="setting-copy">
              <strong>默认模型通道</strong>
              <small>新建任务时优先使用此通道</small>
            </span>
            <select id="model-provider" v-model="modelProvider" @change="saveModelPreference">
              <option value="local">本地</option>
              <option value="cloud">云端</option>
            </select>
          </label>
        </section>

        <section v-else-if="activeSection === 'usage'" class="settings-section">
          <div class="section-heading">
            <p>用量</p>
            <h2>积分与额度</h2>
            <span>查看当前积分、今日额度和最近变动。</span>
          </div>

          <div class="balance-summary">
            <span class="balance-icon"><Coins :size="18" /></span>
            <div>
              <small>可用积分</small>
              <strong>{{ balance?.balance ?? "--" }}</strong>
            </div>
          </div>

          <div class="usage-block">
            <h3>今日额度</h3>
            <div class="usage-list">
              <div v-for="row in usageRows" :key="row.key" class="usage-row">
                <div class="usage-copy">
                  <span>{{ row.label }}</span>
                  <strong>{{ row.used }} / {{ row.limit }}</strong>
                </div>
                <div class="usage-progress" aria-hidden="true">
                  <span :style="{ width: `${row.percent}%` }"></span>
                </div>
              </div>
            </div>
          </div>

          <div class="ledger-block">
            <h3>最近积分变动</h3>
            <ul class="ledger-list">
              <li v-for="row in ledger" :key="row.id">
                <span>{{ row.kind }} · {{ row.biz_type }}</span>
                <strong :class="{ positive: row.change_amount > 0 }">
                  {{ row.change_amount > 0 ? "+" : "" }}{{ row.change_amount }}
                </strong>
              </li>
              <li v-if="!ledger.length" class="empty-row">暂无流水</li>
            </ul>
          </div>
        </section>

        <section v-else-if="activeSection === 'desktop'" class="settings-section">
          <div class="section-heading">
            <p>本地模型</p>
            <h2>本地推理二进制与权重</h2>
            <span>首次使用本地生成前，需下载 llama.cpp / stable-diffusion.cpp 及对应模型权重。</span>
          </div>

          <p v-if="localModelsError" class="error-message" role="alert">{{ localModelsError }}</p>

          <div class="local-model-list">
            <div v-for="row in localModelRows" :key="row.key" class="local-model-row">
              <span class="setting-copy"><strong>{{ row.label }}</strong></span>
              <span :class="['model-status', { ready: row.ready }]">
                {{ row.ready ? "已就绪" : "未下载" }}
              </span>
            </div>
          </div>

          <div v-if="(downloading || buildingAcestep) && downloadProgress" class="download-progress-block">
            <div class="usage-copy">
              <span>{{ downloadProgress.file || downloadProgress.stage }}</span>
              <strong v-if="downloadProgress.total">
                {{ Math.round((downloadProgress.downloaded / downloadProgress.total) * 100) }}%
              </strong>
            </div>
            <div class="usage-progress" aria-hidden="true">
              <span
                :style="{
                  width: downloadProgress.total
                    ? `${Math.min(100, (downloadProgress.downloaded / downloadProgress.total) * 100)}%`
                    : '100%',
                }"
              ></span>
            </div>
          </div>

          <div class="setting-row">
            <span class="setting-copy">
              <strong>{{ localModels?.ready ? "本地模型已就绪" : "下载本地模型" }}</strong>
              <small>下载后自动重启本地推理网关以生效</small>
            </span>
            <button
              class="download-button"
              type="button"
              :disabled="downloading"
              @click="startModelDownload"
            >
              <Download :size="16" />
              {{ downloading ? "下载中…" : localModels?.ready ? "重新下载" : "开始下载" }}
            </button>
          </div>

          <div class="section-heading acestep-heading">
            <p>可选</p>
            <h2>音乐生成(acestep.cpp)</h2>
            <span>
              上游未提供预编译产物，需在本机源码构建；未构建时音乐生成走内置合成兜底。
            </span>
          </div>

          <p v-if="acestepError" class="error-message" role="alert">{{ acestepError }}</p>
          <p v-else-if="acestep && !acestep.toolchain_available" class="hint-message">
            需要 Xcode 命令行工具才能构建：终端执行 <code>xcode-select --install</code> 后重试。
          </p>

          <div v-if="acestep" class="local-model-list">
            <div class="local-model-row">
              <span class="setting-copy"><strong>编译工具链(git/cmake/cc)</strong></span>
              <span :class="['model-status', { ready: acestep.toolchain_available }]">
                {{ acestep.toolchain_available ? "已具备" : "缺失" }}
              </span>
            </div>
            <div class="local-model-row">
              <span class="setting-copy"><strong>acestep.cpp 二进制(源码构建)</strong></span>
              <span :class="['model-status', { ready: acestep.binaries }]">
                {{ acestep.binaries ? "已就绪" : "未构建" }}
              </span>
            </div>
            <div class="local-model-row">
              <span class="setting-copy"><strong>音乐模型权重(ACE-Step-1.5)</strong></span>
              <span :class="['model-status', { ready: acestep.models }]">
                {{ acestep.models ? "已就绪" : "未下载" }}
              </span>
            </div>
          </div>

          <div class="setting-row">
            <span class="setting-copy">
              <strong>{{ acestep?.ready ? "音乐生成已就绪" : "构建音乐生成" }}</strong>
              <small>源码构建 + 下载权重耗时较长（视机器数分钟到十几分钟）</small>
            </span>
            <button
              class="download-button"
              type="button"
              :disabled="buildingAcestep || (acestep && !acestep.toolchain_available)"
              @click="startAcestepBuild"
            >
              <Download :size="16" />
              {{ buildingAcestep ? "构建中…" : acestep?.ready ? "重新构建" : "开始构建" }}
            </button>
          </div>
        </section>

        <section v-else-if="activeSection === 'account'" class="settings-section">
          <div class="section-heading">
            <p>账户</p>
            <h2>个人资料与登录</h2>
            <span>管理公开资料，或退出当前账户。</span>
          </div>

          <RouterLink class="account-link" to="/profile/setup">
            <span class="account-link-icon"><UserRound :size="18" /></span>
            <span class="setting-copy">
              <strong>个人资料</strong>
              <small>修改头像、名称和个人信息</small>
            </span>
            <ChevronRight :size="17" />
          </RouterLink>

          <div v-if="isTauriRuntime() && auth.persistenceMode === 'unavailable'" class="setting-row vault-row">
            <span class="setting-copy">
              <strong><KeyRound :size="15" /> 本地密码保护</strong>
              <small>系统密钥串不可用，设置一个本地密码来记住登录，而不是每次都重新登录</small>
            </span>
            <div class="vault-form">
              <input
                v-model="vaultPassphrase"
                type="password"
                placeholder="设置密码"
                autocomplete="new-password"
              />
              <input
                v-model="vaultConfirmPassphrase"
                type="password"
                placeholder="确认密码"
                autocomplete="new-password"
              />
              <button type="button" :disabled="savingVault" @click="saveVaultPassphrase">
                {{ savingVault ? "保存中…" : "保存" }}
              </button>
            </div>
            <p v-if="vaultError" class="error-message" role="alert">{{ vaultError }}</p>
          </div>

          <div class="danger-zone">
            <div class="setting-copy">
              <strong>退出登录</strong>
              <small>结束当前设备上的登录状态</small>
            </div>
            <button class="logout-button" type="button" :disabled="loggingOut" @click="logout">
              <LogOut :size="16" />
              {{ loggingOut ? "退出中" : "退出登录" }}
            </button>
          </div>
        </section>
      </main>
    </div>
  </section>
</template>

<style scoped>
.settings-page {
  align-content: start;
  display: grid;
  gap: 24px;
  margin: 0 auto;
  max-width: 1060px;
  min-height: 100%;
  padding: 40px 44px 64px;
  width: 100%;
}

.settings-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.settings-eyebrow,
.section-heading p {
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

.logout-button {
  align-items: center;
  border-radius: 7px;
  display: inline-flex;
  font: inherit;
  font-size: 13px;
  font-weight: 750;
  gap: 8px;
  justify-content: center;
  min-height: 38px;
  padding: 0 12px;
  text-decoration: none;
}

.settings-shell {
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
  background: transparent;
  border: 0;
  border-radius: 6px;
  color: var(--color-muted);
  cursor: pointer;
  display: flex;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  gap: 10px;
  min-height: 40px;
  padding: 0 11px;
  position: relative;
  text-align: left;
  width: 100%;
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

.settings-content {
  min-width: 0;
}

.settings-section {
  display: grid;
  gap: 0;
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

.setting-row,
.account-link,
.danger-zone {
  align-items: center;
  border-bottom: 1px solid var(--color-border-soft);
  display: flex;
  gap: 16px;
  justify-content: space-between;
  min-height: 82px;
  padding: 18px 0;
}

.vault-row {
  align-items: stretch;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.vault-row .setting-copy strong {
  align-items: center;
  display: flex;
  gap: 6px;
}

.vault-form {
  display: flex;
  gap: 10px;
}

.vault-form input {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 7px;
  color: var(--color-text);
  flex: 1;
  font: inherit;
  padding: 8px 11px;
}

.vault-form button {
  background: var(--color-accent);
  border: none;
  border-radius: 7px;
  color: var(--color-heading);
  cursor: pointer;
  font: inherit;
  padding: 8px 16px;
  white-space: nowrap;
}

.vault-form button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.setting-copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.setting-copy strong {
  color: var(--color-text);
  font-size: 14px;
}

.setting-copy small,
.balance-summary small {
  color: var(--color-muted);
  font-size: 12px;
}

select {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 7px;
  color: var(--color-text);
  font: inherit;
  min-height: 38px;
  min-width: 112px;
  padding: 0 30px 0 11px;
}

.balance-summary {
  align-items: center;
  border-bottom: 1px solid var(--color-border-soft);
  display: flex;
  gap: 13px;
  padding: 24px 0;
}

.balance-icon,
.account-link-icon {
  align-items: center;
  background: var(--color-accent-soft);
  border-radius: 7px;
  color: var(--color-accent);
  display: inline-flex;
  flex: 0 0 auto;
  height: 38px;
  justify-content: center;
  width: 38px;
}

.balance-summary > div {
  display: grid;
  gap: 2px;
}

.balance-summary strong {
  color: var(--color-heading);
  font-size: 27px;
  line-height: 1.1;
}

.usage-block,
.ledger-block {
  border-bottom: 1px solid var(--color-border-soft);
  padding: 22px 0;
}

.usage-block h3,
.ledger-block h3 {
  color: var(--color-muted-strong);
  font-size: 12px;
  margin-bottom: 16px;
}

.usage-list {
  display: grid;
  gap: 15px;
}

.usage-row {
  display: grid;
  gap: 8px;
}

.usage-copy {
  align-items: center;
  display: flex;
  font-size: 13px;
  justify-content: space-between;
}

.usage-copy span {
  color: var(--color-text);
}

.usage-copy strong {
  color: var(--color-muted-strong);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.usage-progress {
  background: var(--color-panel-strong);
  border-radius: 3px;
  height: 5px;
  overflow: hidden;
}

.usage-progress span {
  background: var(--color-accent);
  display: block;
  height: 100%;
}

.ledger-list {
  display: grid;
  list-style: none;
  margin: 0;
  padding: 0;
}

.ledger-list li {
  align-items: center;
  border-top: 1px solid var(--color-border-soft);
  display: flex;
  font-size: 13px;
  gap: 16px;
  justify-content: space-between;
  min-height: 43px;
}

.ledger-list li:first-child {
  border-top: 0;
}

.ledger-list li > span,
.empty-row {
  color: var(--color-muted);
}

.ledger-list strong {
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.ledger-list strong.positive {
  color: var(--color-success);
}

.local-model-list {
  border-bottom: 1px solid var(--color-border-soft);
  display: grid;
  padding: 6px 0 20px;
}

.local-model-row {
  align-items: center;
  display: flex;
  justify-content: space-between;
  min-height: 44px;
}

.model-status {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 700;
}

.model-status.ready {
  color: var(--color-success);
}

.download-progress-block {
  border-bottom: 1px solid var(--color-border-soft);
  display: grid;
  gap: 8px;
  padding: 18px 0;
}

.download-button {
  align-items: center;
  background: var(--color-accent);
  border: 0;
  border-radius: 7px;
  color: var(--color-heading);
  cursor: pointer;
  display: inline-flex;
  flex: 0 0 auto;
  font: inherit;
  font-size: 13px;
  font-weight: 750;
  gap: 8px;
  min-height: 38px;
  padding: 0 14px;
}

.download-button:hover:not(:disabled) {
  filter: brightness(1.08);
}

.download-button:disabled {
  cursor: wait;
  opacity: 0.62;
}

.account-link {
  color: var(--color-muted);
  justify-content: start;
  text-decoration: none;
}

.account-link .setting-copy {
  flex: 1;
}

.account-link:hover .setting-copy strong {
  color: var(--color-heading);
}

.danger-zone {
  border-bottom: 0;
  margin-top: 16px;
}

.danger-zone .setting-copy strong {
  color: var(--color-danger);
}

.logout-button {
  background: transparent;
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
  cursor: pointer;
  flex: 0 0 auto;
}

.logout-button:hover:not(:disabled) {
  background: var(--color-danger-soft);
}

.logout-button:disabled {
  cursor: wait;
  opacity: 0.62;
}

.error-message {
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  border-radius: 7px;
  color: var(--color-danger);
  margin: 0;
  padding: 11px 13px;
}

.hint-message {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 7px;
  color: var(--color-muted-strong);
  font-size: 13px;
  margin: 0;
  padding: 11px 13px;
}

.hint-message code {
  background: var(--color-panel);
  border-radius: 4px;
  padding: 1px 5px;
}

.acestep-heading {
  margin-top: 8px;
}

.settings-nav-item:focus-visible,
.account-link:focus-visible,
.logout-button:focus-visible,
.download-button:focus-visible,
select:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

@media (max-width: 720px) {
  .settings-page {
    gap: 20px;
    padding: 28px 20px 48px;
  }

  .settings-shell {
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
  .settings-header {
    align-items: flex-start;
  }

  .setting-row,
  .danger-zone {
    align-items: stretch;
    flex-direction: column;
  }

  .setting-row select,
  .logout-button {
    width: 100%;
  }
}
</style>
