<script setup>
import { computed, onMounted, ref } from "vue";
import { ListMusic, Music2, Play, RefreshCw, Radio, Square, Upload } from "@lucide/vue";
import { usePlayerStore } from "../stores/player";
import { usePlaylistStore } from "../stores/playlist";
import { uploadLocalImport } from "../services/music";
import { selectedApiTarget } from "../services/http";

const player = usePlayerStore();
const playlist = usePlaylistStore();
const error = ref("");
const importing = ref(false);

// 方案 B:流式生成播放
const streamPrompt = ref("夏夜骑行的轻快电子乐");

async function startStream() {
  try {
    await player.streamGenerate({ prompt: streamPrompt.value, seconds: 8, target: selectedApiTarget(), channels: 2 });
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

const tracks = computed(() =>
  playlist.activeItems.map((item) => ({
    id: item.id,
    title: item.title || "未命名歌曲",
    artist: item.artist || "未知艺人",
    source: item.source,
    url: item.source_ref,
  })),
);

async function refreshPlaylist() {
  error.value = "";
  try {
    await playlist.sync();
    player.setQueue(tracks.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function onImportFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  importing.value = true;
  error.value = "";
  try {
    await uploadLocalImport({ file, mime: file.type, filename: file.name });
    await refreshPlaylist();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    importing.value = false;
  }
}

onMounted(refreshPlaylist);
</script>

<template>
  <section class="music-page">
    <header class="page-header">
      <div>
        <p>音乐</p>
        <h1>音乐播放器</h1>
      </div>
      <div class="header-actions">
        <button type="button" @click="refreshPlaylist"><RefreshCw :size="16" /> 刷新</button>
        <label class="import-button">
          <Upload :size="16" />
          {{ importing ? "导入中" : "导入" }}
          <input accept="audio/*" type="file" @change="onImportFile" />
        </label>
      </div>
    </header>

    <p v-if="error" class="error-message">{{ error }}</p>

    <article class="stream-panel">
      <div class="panel-title">
        <Radio :size="17" />
        <h2>流式生成播放(边生成边播)</h2>
      </div>
      <div class="stream-controls">
        <input v-model="streamPrompt" class="stream-input" placeholder="描述想生成的音乐" />
        <button v-if="!player.isStreaming" class="stream-btn" type="button" @click="startStream">
          <Play :size="16" /> 生成并播放
        </button>
        <button v-else class="stream-btn stop" type="button" @click="player.stopStream">
          <Square :size="16" /> 停止
        </button>
      </div>
      <p class="stream-status">
        状态:<strong>{{ player.streamState }}</strong>
        <span v-if="player.streamError" class="stream-err"> · {{ player.streamError }}</span>
      </p>
    </article>

    <section class="player-layout">
      <article class="player-panel">
        <div class="cover-block">
          <Music2 :size="48" />
        </div>
        <div class="track-copy">
          <span>当前播放</span>
          <h2>{{ player.currentTrack?.title || "暂无歌曲" }}</h2>
          <p>{{ player.currentTrack?.artist || "从播放队列选择一首歌" }}</p>
        </div>
        <button class="play-button" type="button" :disabled="!player.currentTrack" @click="player.togglePlay">
          <Play :size="20" />
          {{ player.isPlaying ? "暂停" : "播放" }}
        </button>
      </article>

      <article class="queue-panel">
        <div class="panel-title">
          <ListMusic :size="17" />
          <h2>播放队列</h2>
        </div>
        <button
          v-for="(track, index) in tracks"
          :key="track.id"
          :class="['queue-row', { active: player.currentTrack?.id === track.id }]"
          type="button"
          @click="player.playAt(index)"
        >
          <span>{{ index + 1 }}</span>
          <strong>{{ track.title }}</strong>
          <small>{{ track.artist }}</small>
        </button>
        <p v-if="!tracks.length" class="empty-state">暂无歌曲</p>
      </article>
    </section>
  </section>
</template>

<style scoped>
.music-page {
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

.header-actions {
  display: flex;
  gap: 8px;
}

.header-actions button,
.import-button {
  align-items: center;
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text);
  display: inline-flex;
  font: inherit;
  font-weight: 800;
  gap: 8px;
  min-height: 36px;
  padding: 0 12px;
}

.import-button input {
  display: none;
}

.stream-panel {
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
}

.stream-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.stream-input {
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text);
  flex: 1 1 280px;
  font: inherit;
  min-height: 38px;
  padding: 0 12px;
}

.stream-btn {
  align-items: center;
  background: var(--color-accent-strong);
  border: 0;
  border-radius: 8px;
  color: var(--color-heading);
  display: inline-flex;
  font: inherit;
  font-weight: 800;
  gap: 8px;
  min-height: 38px;
  padding: 0 16px;
}

.stream-btn.stop {
  background: var(--color-danger);
}

.stream-status {
  color: var(--color-muted);
  font-size: 13px;
  margin: 10px 0 0;
}

.stream-err {
  color: var(--color-danger);
}

.player-layout {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(360px, 0.52fr) minmax(0, 1fr);
}

.player-panel,
.queue-panel {
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
}

.player-panel {
  align-content: start;
  display: grid;
  gap: 18px;
}

.cover-block {
  align-items: center;
  aspect-ratio: 1;
  background: linear-gradient(135deg, #0c2a46, #0b3c4a);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-accent);
  display: flex;
  justify-content: center;
}

.track-copy span {
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 800;
}

.track-copy h2 {
  font-size: 22px;
  margin-top: 5px;
}

.track-copy p {
  color: var(--color-muted-strong);
  margin: 4px 0 0;
}

.play-button {
  align-items: center;
  background: var(--color-accent-strong);
  border: 0;
  border-radius: 8px;
  color: var(--color-heading);
  display: inline-flex;
  font: inherit;
  font-weight: 900;
  gap: 8px;
  justify-content: center;
  min-height: 42px;
}

.panel-title {
  align-items: center;
  color: var(--color-muted-strong);
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.queue-panel {
  display: grid;
  gap: 8px;
}

.queue-row {
  align-items: center;
  background: var(--color-panel-strong);
  border: 1px solid var(--color-border-soft);
  border-radius: 8px;
  color: var(--color-text);
  display: grid;
  font: inherit;
  gap: 10px;
  grid-template-columns: 30px minmax(0, 1fr) minmax(90px, 0.35fr);
  min-height: 44px;
  padding: 0 10px;
  text-align: left;
}

.queue-row.active {
  background: var(--color-accent-soft);
  border-color: var(--color-accent);
}

.queue-row span,
.queue-row small {
  color: var(--color-muted);
}

.queue-row strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-state,
.error-message {
  border-radius: 8px;
  margin: 0;
  padding: 10px 12px;
}

.empty-state {
  border: 1px dashed var(--color-border);
  color: var(--color-muted);
}

.error-message {
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
}
</style>
