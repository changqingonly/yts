<script setup>
import { computed, onMounted, ref } from "vue";
import { Clipboard, Image, Music4, Sparkles } from "@lucide/vue";
import { fetchDailyUsage } from "../services/credits";
import { listSongs } from "../services/songs";

const activeTab = ref("songs");
const songs = ref([]);
const dailyUsage = ref(null);
const error = ref("");
const message = ref("");

const tabs = [
  { id: "songs", label: "歌曲灵感", icon: Sparkles },
  { id: "images", label: "图片大全", icon: Image },
  { id: "audio", label: "音频特效", icon: Music4 },
];

const imageQuota = computed(() => dailyUsage.value?.images ?? { used: 0, limit: 100 });
const audioQuota = computed(() => dailyUsage.value?.audio_effects ?? { used: 0, limit: 100 });

async function loadAssets() {
  error.value = "";
  songs.value = await listSongs();
  dailyUsage.value = await fetchDailyUsage();
}

function formatLyric(lyric) {
  return lyric
    .replace(/\r\n/g, "\n")
    .replace(/\s*(\[(?:Intro|Verse|Pre-Chorus|Chorus|Bridge|Outro|Final Chorus|Hook)[^\]]*\])/gi, "\n\n$1\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
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

onMounted(loadAssets);
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p>资产</p>
        <h1>资产</h1>
      </div>
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

    <section v-if="activeTab === 'songs'" class="asset-workbench">
      <section class="asset-library">
        <div class="library-head">
          <div>
            <span>资产库</span>
            <h2>歌曲灵感</h2>
          </div>
          <strong>{{ songs.length }} 条</strong>
        </div>

        <div v-if="songs.length" class="song-card-grid">
          <article v-for="song in songs" :key="song.id" class="song-card">
            <header>
              <div>
                <span>歌名</span>
                <h3>{{ song.name }}</h3>
              </div>
              <button class="copy-title" type="button" @click="copyAssetText('歌名', song.name)">
                <Clipboard :size="14" />
                复制歌名
              </button>
            </header>

            <section class="prompt-block">
              <span>原始 Prompt</span>
              <p>{{ song.prompt }}</p>
            </section>

            <dl>
              <div class="preview-block">
                <div class="preview-head">
                  <dt>Suno Style Prompt</dt>
                  <button class="copy-field" type="button" @click="copyAssetText('Suno Style Prompt', song.style_prompt)">
                    <Clipboard :size="14" />
                    复制
                  </button>
                </div>
                <dd>{{ song.style_prompt }}</dd>
              </div>
              <div class="preview-block">
                <div class="preview-head">
                  <dt>Lyric</dt>
                  <button class="copy-field" type="button" @click="copyAssetText('歌词', formatLyric(song.lyric_prompt))">
                    <Clipboard :size="14" />
                    复制
                  </button>
                </div>
                <dd class="lyric-text">{{ formatLyric(song.lyric_prompt) }}</dd>
              </div>
            </dl>
          </article>
        </div>

        <div v-else class="asset-empty">
          <Sparkles :size="28" />
          <h2>暂无歌曲灵感</h2>
          <p>从创作页保存最终结果后，可以在这里快速扫读和复用。</p>
        </div>
      </section>
    </section>

    <section v-else-if="activeTab === 'images'" class="building-panel">
      <Image :size="28" />
      <h2>图片大全</h2>
      <p>待建设。图片生成额度：{{ imageQuota.used }}/{{ imageQuota.limit }}</p>
    </section>

    <section v-else class="building-panel">
      <Music4 :size="28" />
      <h2>音频特效</h2>
      <p>待建设。音频特效额度：{{ audioQuota.used }}/{{ audioQuota.limit }}</p>
    </section>
  </section>
</template>

<style scoped>
.page {
  display: grid;
  gap: 14px;
  padding: 24px 28px;
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

.asset-toolbar {
  align-items: center;
  display: flex;
  justify-content: flex-start;
}

.asset-tabs {
  background: transparent;
  display: flex;
  gap: 6px;
  padding: 0;
}

.asset-tabs button {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 6px;
  color: var(--color-muted-strong);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-weight: 800;
  gap: 6px;
  min-height: 32px;
  padding: 0 10px;
  transition:
    background 160ms ease,
    color 160ms ease,
    transform 160ms ease;
}

.asset-tabs button:hover,
.asset-tabs button:focus-visible {
  background: rgba(14, 165, 233, 0.1);
  box-shadow: inset 0 0 0 1px rgba(14, 165, 233, 0.2);
  color: var(--color-accent);
  outline: 2px solid rgba(14, 165, 233, 0.42);
  outline-offset: 2px;
  transform: translateY(-1px);
}

.asset-tabs button.active {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.asset-tabs button.active:hover,
.asset-tabs button.active:focus-visible {
  background: rgba(14, 165, 233, 0.18);
}

.asset-workbench {
  align-items: start;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
}

.asset-library,
.song-card,
.building-panel {
  background: var(--color-panel);
  border-radius: 8px;
}

.library-head,
.song-card header,
.preview-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.library-head h2,
.library-head span,
.song-card h3 {
  margin: 0;
}

.library-head h2 {
  font-size: 18px;
}

.library-head span,
.song-card span,
.prompt-block span {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 800;
}

dt {
  color: var(--color-muted-strong);
  font-size: 13px;
  font-weight: 800;
}

.copy-title,
.copy-field {
  align-items: center;
  background: var(--color-accent-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: 999px;
  color: var(--color-accent);
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
.copy-field:hover {
  background: rgba(14, 165, 233, 0.18);
  border-color: var(--color-accent);
}

.asset-library {
  align-content: start;
  display: grid;
  gap: 14px;
  min-height: 520px;
  padding: 16px;
}

.library-head {
  border-bottom: 1px solid var(--color-border-soft);
  padding-bottom: 12px;
}

.library-head strong {
  background: var(--color-accent-soft);
  border-radius: 999px;
  color: var(--color-accent);
  font-size: 12px;
  padding: 6px 10px;
  white-space: nowrap;
}

.song-card-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.song-card {
  display: grid;
  gap: 12px;
  padding: 14px;
}

.song-card header > div {
  min-width: 0;
}

.song-card h3 {
  font-size: 18px;
  overflow-wrap: anywhere;
}

.song-card p,
.building-panel p,
dd {
  color: var(--color-muted-strong);
}

.prompt-block {
  background: rgba(14, 165, 233, 0.06);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: grid;
  gap: 5px;
  padding: 10px;
}

.prompt-block p,
dd {
  margin: 0;
  overflow-wrap: anywhere;
}

dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.preview-block {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  display: grid;
  gap: 5px;
  padding: 10px;
}

.lyric-text {
  line-height: 1.45;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.building-panel {
  align-content: center;
  color: var(--color-muted-strong);
  display: grid;
  gap: 10px;
  justify-items: center;
  min-height: 380px;
  padding: 30px;
  text-align: center;
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
  background: var(--color-panel-strong);
  border: 1px dashed var(--color-border);
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
  .asset-workbench {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
