<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Clipboard, Image, Music4, Sparkles, X } from "@lucide/vue";
import { fetchDailyUsage } from "../services/credits";
import { listSongs } from "../services/songs";
import { useEnvironmentStore } from "../stores/environment";

const environment = useEnvironmentStore();

const activeTab = ref("songs");
const songs = ref([]);
const dailyUsage = ref(null);
const error = ref("");
const message = ref("");
const selectedAssetKey = ref("");

const assetTypeMeta = {
  songs: {
    id: "songs",
    label: "歌曲灵感",
    icon: Sparkles,
    titleLabel: "歌名",
    primaryLabel: "原始 prompt",
    secondaryLabel: "Style Prompt",
    bodyLabel: "Lyric",
    emptyTitle: "暂无歌曲灵感",
    emptyDescription: "从创作页保存最终结果后，会在这里按时间排列。",
  },
  images: {
    id: "images",
    label: "图片大全",
    icon: Image,
    titleLabel: "图片标题",
    primaryLabel: "图片 prompt",
    secondaryLabel: "画面信息",
    bodyLabel: "图片详情",
    emptyTitle: "暂无图片资产",
    emptyDescription: "图片资产接口接入后，会在这里使用相同的列表和详情抽屉。",
  },
  audio: {
    id: "audio",
    label: "音频特效",
    icon: Music4,
    titleLabel: "音频标题",
    primaryLabel: "音频 prompt",
    secondaryLabel: "音色信息",
    bodyLabel: "音频详情",
    emptyTitle: "暂无音频特效",
    emptyDescription: "音频特效资产接口接入后，会在这里使用相同的列表和详情抽屉。",
  },
};

const tabs = Object.values(assetTypeMeta);

const imageQuota = computed(() => dailyUsage.value?.images ?? { used: 0, limit: 100 });
const audioQuota = computed(() => dailyUsage.value?.audio_effects ?? { used: 0, limit: 100 });
const songAssetRows = computed(() =>
  songs.value.map((song) => ({
    key: `song:${song.id}`,
    id: song.id,
    title: song.name,
    primaryText: song.prompt,
    secondaryText: song.style_prompt,
    detailText: formatLyric(song.lyric_prompt),
    time: song.update_time ?? song.create_time,
    type: "songs",
  })),
);
const imageAssetRows = computed(() => []);
const audioAssetRows = computed(() => []);
const visibleAssets = computed(() => {
  if (activeTab.value === "songs") {
    return songAssetRows.value;
  }
  if (activeTab.value === "images") {
    return imageAssetRows.value;
  }
  return audioAssetRows.value;
});
const activeTabMeta = computed(() => assetTypeMeta[activeTab.value]);
const assetTitleLabel = computed(() => activeTabMeta.value.titleLabel);
const assetPrimaryLabel = computed(() => activeTabMeta.value.primaryLabel);
const assetSecondaryLabel = computed(() => activeTabMeta.value.secondaryLabel);
const activeQuota = computed(() => {
  if (activeTab.value === "images") {
    return imageQuota.value;
  }
  if (activeTab.value === "audio") {
    return audioQuota.value;
  }
  return null;
});
const selectedAsset = computed(() => {
  if (!selectedAssetKey.value) {
    return null;
  }
  return visibleAssets.value.find((item) => item.key === selectedAssetKey.value) ?? null;
});

async function loadAssets() {
  error.value = "";
  try {
    songs.value = await listSongs();
    dailyUsage.value = await fetchDailyUsage();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function formatLyric(lyric) {
  return lyric
    .replace(/\r\n/g, "\n")
    .replace(/\s*(\[(?:Intro|Verse|Pre-Chorus|Chorus|Bridge|Outro|Final Chorus|Hook)[^\]]*\])/gi, "\n\n$1\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function formatAssetTime(value) {
  if (!value) {
    return "未记录";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return `时间格式错误：${value}`;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function selectAsset(item) {
  selectedAssetKey.value = item.key;
}

function handlePageClick(event) {
  const target = event.target;
  if (!(target instanceof Element)) {
    selectedAssetKey.value = "";
    return;
  }
  if (target.closest(".asset-row")) {
    return;
  }
  selectedAssetKey.value = "";
}

async function copyAssetText(label, text) {
  message.value = "";
  error.value = "";
  try {
    await navigator.clipboard.writeText(text);
    message.value = `已复制${label}`;
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    error.value = `复制${label}失败：${reason}`;
  }
}

watch(activeTab, () => {
  selectedAssetKey.value = "";
});

// 本地服务是惰性启动的(见 stores/environment.js),首次挂载时大概率还没就绪;一旦健康检查
// 转为 online 就自动重试一次,而不需要用户手动刷新页面。
watch(
  () => environment.targetHealth(environment.target),
  async (status) => {
    if (status === "online" && error.value) await loadAssets();
  },
);

onMounted(loadAssets);
</script>

<template>
  <section class="page" @click="handlePageClick">
    <header class="page-header">
      <h1>资产</h1>
    </header>

    <div class="asset-toolbar">
      <div class="asset-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :class="{ active: activeTab === tab.id }"
          type="button"
          @click="activeTab = tab.id"
        >
          <component :is="tab.icon" :size="15" />
          {{ tab.label }}
        </button>
      </div>
    </div>

    <p v-if="message" class="ok-message">{{ message }}</p>
    <p v-if="error" class="error-message">{{ error }}</p>

    <section class="asset-workbench">
      <section class="asset-library">
        <div class="library-head">
          <div>
            <h2>{{ activeTabMeta.label }}</h2>
          </div>
          <strong v-if="activeQuota">{{ activeQuota.used }}/{{ activeQuota.limit }}</strong>
          <strong v-else>{{ visibleAssets.length }} 条</strong>
        </div>

        <div class="asset-list-head">
          <span>{{ assetTitleLabel }}</span>
          <span>{{ assetPrimaryLabel }}</span>
          <span>时间</span>
        </div>

        <div v-if="visibleAssets.length" class="asset-list">
          <button
            v-for="item in visibleAssets"
            :key="item.key"
            :class="['asset-row', { selected: selectedAsset?.key === item.key }]"
            type="button"
            @click.stop="selectAsset(item)"
          >
            <span class="asset-title-cell">{{ item.title }}</span>
            <span class="asset-prompt-cell">{{ item.primaryText }}</span>
            <time :datetime="item.time">{{ formatAssetTime(item.time) }}</time>
          </button>
        </div>

        <div v-else class="asset-empty">
          <component :is="activeTabMeta.icon" :size="28" />
          <h2>{{ activeTabMeta.emptyTitle }}</h2>
          <p>{{ activeTabMeta.emptyDescription }}</p>
        </div>
      </section>

    </section>

    <Teleport to="body">
      <div v-if="selectedAsset" class="asset-drawer-layer">
        <aside class="asset-detail-drawer" role="dialog" aria-modal="false" aria-label="资产详情">
          <header class="drawer-head">
            <div>
              <span>{{ activeTabMeta.label }}</span>
              <h2>{{ selectedAsset.title }}</h2>
            </div>
            <div class="drawer-actions">
              <button
                v-if="activeTab === 'songs'"
                class="copy-title"
                type="button"
                @click="copyAssetText('歌名', selectedAsset.title)"
              >
                <Clipboard :size="14" />
                复制歌名
              </button>
              <button v-else class="copy-title" type="button" @click="copyAssetText(assetTitleLabel, selectedAsset.title)">
                <Clipboard :size="14" />
                复制
              </button>
              <button class="drawer-close" type="button" aria-label="关闭详情" @click="selectedAssetKey = ''">
                <X :size="16" />
              </button>
            </div>
          </header>

          <section class="detail-section">
            <span>{{ assetPrimaryLabel }}</span>
            <p class="prompt-text">{{ selectedAsset.primaryText }}</p>
          </section>

          <section v-if="selectedAsset.secondaryText" class="detail-section preview-block">
            <div class="preview-head">
              <h3>{{ assetSecondaryLabel }}</h3>
              <button
                v-if="activeTab === 'songs'"
                class="copy-field"
                type="button"
                @click="copyAssetText('Style Prompt', selectedAsset.secondaryText)"
              >
                <Clipboard :size="14" />
                复制
              </button>
              <button
                v-else
                class="copy-field"
                type="button"
                @click="copyAssetText(assetSecondaryLabel, selectedAsset.secondaryText)"
              >
                <Clipboard :size="14" />
                复制
              </button>
            </div>
            <p>{{ selectedAsset.secondaryText }}</p>
          </section>

          <section v-if="selectedAsset.detailText" class="detail-section preview-block">
            <div class="preview-head">
              <h3>{{ activeTabMeta.bodyLabel }}</h3>
              <button
                v-if="activeTab === 'songs'"
                class="copy-field"
                type="button"
                @click="copyAssetText('歌词', selectedAsset.detailText)"
              >
                <Clipboard :size="14" />
                复制
              </button>
              <button v-else class="copy-field" type="button" @click="copyAssetText(activeTabMeta.bodyLabel, selectedAsset.detailText)">
                <Clipboard :size="14" />
                复制
              </button>
            </div>
            <p class="lyric-text">{{ selectedAsset.detailText }}</p>
          </section>
        </aside>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.page {
  background:
    linear-gradient(110deg, rgba(34, 211, 238, 0.07), transparent 34%),
    linear-gradient(180deg, rgba(8, 25, 42, 0.2) 0%, rgba(9, 35, 50, 0.1) 42%, rgba(4, 16, 31, 0) 100%);
  display: grid;
  gap: 18px;
  min-height: 100%;
  padding: 26px 30px;
}

.page-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

h1,
h2 {
  margin: 0;
}

h1 {
  font-size: 26px;
  line-height: 1.08;
}

.asset-toolbar {
  align-items: center;
  display: flex;
  justify-content: flex-start;
}

.asset-tabs {
  background: transparent;
  display: flex;
  gap: 10px;
  padding: 0;
}

.asset-tabs button {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 8px;
  color: var(--color-muted-strong);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-weight: 800;
  gap: 6px;
  min-height: 34px;
  padding: 0 12px;
  transition:
    background 160ms ease,
    box-shadow 160ms ease,
    color 160ms ease,
    transform 160ms ease;
}

.asset-tabs button:hover,
.asset-tabs button:focus-visible {
  background: rgba(34, 211, 238, 0.11);
  box-shadow: 0 10px 24px rgba(2, 8, 20, 0.18);
  color: #9cecff;
  outline: 2px solid rgba(14, 165, 233, 0.42);
  outline-offset: 2px;
  transform: translateY(-1px);
}

.asset-tabs button.active {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.28), rgba(20, 184, 166, 0.16));
  box-shadow: 0 14px 30px rgba(2, 8, 20, 0.22);
  color: #7dd3fc;
}

.asset-tabs button.active:hover,
.asset-tabs button.active:focus-visible {
  background: rgba(14, 165, 233, 0.24);
}

.asset-workbench {
  align-items: start;
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(0, 1fr);
}

.asset-library {
  --asset-list-columns: minmax(180px, 0.78fr) minmax(280px, 1.42fr) 118px;

  align-content: start;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  display: grid;
  gap: 16px;
  min-height: 520px;
  padding: 8px 0 24px;
}

.library-head,
.drawer-head,
.preview-head {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.library-head {
  padding: 0 4px 8px;
}

.library-head > div {
  min-width: 0;
}

.library-head h2,
.drawer-head h2,
.drawer-head span {
  margin: 0;
}

.library-head h2 {
  color: #e7f5ff;
  font-size: 18px;
  letter-spacing: 0;
}

.drawer-head span,
.detail-section > span {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 800;
}

.asset-detail-drawer .drawer-head span,
.asset-detail-drawer .detail-section > span {
  color: #9fb9cf;
}

.library-head strong {
  background: rgba(20, 184, 166, 0.12);
  border-radius: 999px;
  color: #7dd3fc;
  font-size: 12px;
  padding: 6px 10px;
  white-space: nowrap;
}

.asset-list-head,
.asset-row {
  display: grid;
  gap: 16px;
  grid-template-columns: var(--asset-list-columns);
}

.asset-list-head {
  align-items: center;
  color: #7898b4;
  font-size: 12px;
  font-weight: 900;
  justify-items: start;
  padding: 0 14px;
}

.asset-list-head span:last-child {
  justify-self: end;
  text-align: right;
}

.asset-list {
  display: grid;
  gap: 0;
}

.asset-row {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 0;
  color: var(--color-text);
  cursor: pointer;
  font: inherit;
  min-height: 56px;
  padding: 10px 14px;
  position: relative;
  text-align: left;
  transition:
    background 160ms ease,
    box-shadow 160ms ease,
    transform 160ms ease;
}

.asset-row::after {
  background: linear-gradient(90deg, rgba(125, 211, 252, 0.08), transparent 76%);
  bottom: 0;
  content: "";
  height: 1px;
  left: 14px;
  position: absolute;
  right: 14px;
}

.asset-row:hover,
.asset-row:focus-visible,
.asset-row.selected {
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.18), rgba(20, 184, 166, 0.08) 58%, transparent);
  box-shadow: inset 3px 0 0 var(--color-accent), 0 14px 32px rgba(2, 8, 20, 0.16);
  outline: 0;
  transform: translateX(2px);
}

.asset-title-cell {
  color: var(--color-heading);
  font-size: 14px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-prompt-cell {
  font-size: 13px;
}

.asset-prompt-cell,
.asset-row time {
  color: var(--color-muted-strong);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-row time {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  justify-self: end;
  text-align: right;
  width: 100%;
}

.asset-drawer-layer {
  inset: 0;
  pointer-events: none;
  position: fixed;
  z-index: 40;
}

.asset-detail-drawer {
  align-content: start;
  background: linear-gradient(180deg, #163955 0%, #0b2135 100%);
  border-left: 0;
  border-radius: 0;
  bottom: 0;
  box-shadow:
    -28px 0 70px rgba(1, 8, 18, 0.42),
    inset 1px 0 0 rgba(125, 211, 252, 0.08);
  color: #dcebf8;
  color-scheme: dark;
  display: grid;
  gap: 16px;
  height: 100vh;
  overflow: auto;
  padding: 26px 24px 30px;
  pointer-events: auto;
  position: absolute;
  right: 0;
  top: 0;
  width: min(560px, calc(100vw - 72px));
}

.drawer-head {
  padding-bottom: 10px;
}

.drawer-head h2 {
  color: #f0f7ff;
  font-size: 24px;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.drawer-actions {
  align-items: center;
  display: inline-flex;
  gap: 7px;
}

.copy-title,
.copy-field,
.drawer-close {
  align-items: center;
  background: rgba(14, 165, 233, 0.18);
  border: 0;
  border-radius: 999px;
  color: #a5f3fc;
  cursor: pointer;
  display: inline-flex;
  flex: 0 0 auto;
  font: inherit;
  font-size: 12px;
  font-weight: 900;
  gap: 5px;
  min-height: 28px;
  padding: 0 9px;
}

.copy-title:hover,
.copy-field:hover,
.drawer-close:hover {
  background: rgba(20, 184, 166, 0.24);
  color: #e0f2fe;
}

.drawer-close {
  border-radius: 8px;
  justify-content: center;
  padding: 0;
  width: 30px;
}

.detail-section {
  background: linear-gradient(180deg, rgba(12, 35, 55, 0.86), rgba(8, 25, 42, 0.76));
  border: 0;
  border-radius: 10px;
  box-shadow: inset 0 1px 0 rgba(125, 211, 252, 0.1);
  display: grid;
  gap: 8px;
  padding: 15px;
}

.detail-section p,
.preview-block p {
  color: #d7e8f7;
  margin: 0;
  overflow-wrap: anywhere;
}

h3 {
  color: #abc9df;
  font-size: 13px;
  font-weight: 800;
  margin: 0;
}

.preview-block {
  background: linear-gradient(180deg, rgba(10, 31, 50, 0.9), rgba(7, 22, 37, 0.82));
}

.prompt-text {
  color: #edf7ff;
  font-size: 16px;
  line-height: 1.55;
}

.lyric-text {
  line-height: 1.45;
  max-height: 460px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.asset-empty,
.ok-message,
.error-message {
  border-radius: 8px;
  margin: 0;
  padding: 10px 12px;
}

.asset-empty {
  align-self: center;
  background: linear-gradient(180deg, rgba(15, 46, 70, 0.48), rgba(8, 24, 39, 0.4));
  border: 0;
  box-shadow: inset 0 1px 0 rgba(125, 211, 252, 0.1);
  color: var(--color-muted-strong);
  display: grid;
  gap: 8px;
  justify-items: center;
  margin: 80px auto 0;
  max-width: 360px;
  padding: 28px;
  text-align: center;
}

.asset-empty svg {
  color: var(--color-muted);
}

.asset-empty h2,
.asset-empty p {
  margin: 0;
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

@media (max-width: 980px) {
  .asset-library {
    --asset-list-columns: minmax(120px, 0.78fr) minmax(160px, 1.42fr) 100px;
  }

  .asset-detail-drawer {
    right: 0;
    top: 0;
    width: min(440px, calc(100vw - 40px));
  }
}
</style>
