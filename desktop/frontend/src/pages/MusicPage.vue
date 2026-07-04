<script setup>
import { computed, onMounted, ref } from "vue";
import {
  Disc3,
  History,
  ListMusic,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Repeat1,
  Repeat2,
  Shuffle,
  SkipBack,
  SkipForward,
  Square,
  Upload,
  X,
} from "@lucide/vue";
import { usePlayerStore } from "../stores/player";
import { usePlaylistStore } from "../stores/playlist";
import { uploadLocalImport } from "../services/music";
import { selectedApiTarget } from "../services/http";

const player = usePlayerStore();
const playlist = usePlaylistStore();
const error = ref("");
const importing = ref(false);
const streamPrompt = ref("夏夜骑行的轻快电子乐");
const playlistDrawerOpen = ref(false);
const drawerMode = ref("queue");
const loopMode = ref("queue");
const playHistory = ref([]);

const loopModes = [
  { key: "queue", label: "循环播放", icon: Repeat2 },
  { key: "single", label: "单曲循环", icon: Repeat1 },
  { key: "shuffle", label: "随机播放", icon: Shuffle },
];

const waveBars = [
  34, 50, 68, 44, 82, 58, 76, 92, 48, 70, 86, 54, 78, 64, 96, 52, 74, 88, 60, 80, 42, 72, 90, 56,
  84, 46, 68, 94, 62, 78, 50, 86, 58, 72, 40, 66, 82, 54, 76, 48, 88, 60, 70, 44,
];

const tracks = computed(() =>
  playlist.activeItems.map((item) => ({
    id: item.id,
    title: item.title || "未命名歌曲",
    artist: item.artist || "未知艺人",
    source: item.source,
    url: item.source_ref,
  })),
);

const currentTrack = computed(() => player.currentTrack || tracks.value[0] || null);
const activeLoopMode = computed(() => loopModes.find((item) => item.key === loopMode.value) || loopModes[0]);
const totalSeconds = computed(() => {
  if (!currentTrack.value) return 0;
  return Math.max(0, Math.round(player.duration || 224 + player.currentIndex * 11));
});
const elapsedSeconds = computed(() => {
  if (!currentTrack.value) return 0;
  const seededProgress = player.isPlaying ? 72 + player.currentIndex * 7 : player.currentTime;
  return Math.min(totalSeconds.value, Math.max(0, Math.round(player.currentTime || seededProgress || 0)));
});
const progressPercent = computed(() => {
  if (!totalSeconds.value) return 0;
  return Math.round((elapsedSeconds.value / totalSeconds.value) * 100);
});
const drawerTracks = computed(() => (drawerMode.value === "history" ? playHistory.value : tracks.value));

async function refreshPlaylist() {
  error.value = "";
  try {
    await playlist.sync();
    player.setQueue(tracks.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function startStreamPreview() {
  if (player.isStreaming) {
    player.stopStream();
    return;
  }
  try {
    await player.streamGenerate({ prompt: streamPrompt.value, seconds: 8, target: selectedApiTarget(), channels: 2 });
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
    event.target.value = "";
  }
}

function togglePlay() {
  error.value = "";
  try {
    player.togglePlay();
    if (player.isPlaying) recordHistory(currentTrack.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function playTrack(index) {
  error.value = "";
  try {
    player.playAt(index);
    recordHistory(tracks.value[index]);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function playDrawerTrack(track, index) {
  const targetIndex = drawerMode.value === "history" ? tracks.value.findIndex((item) => item.id === track.id) : index;
  if (targetIndex >= 0) playTrack(targetIndex);
}

function previousTrack() {
  if (!tracks.value.length) return;
  const previousIndex = (player.currentIndex - 1 + tracks.value.length) % tracks.value.length;
  playTrack(previousIndex);
}

function nextTrack() {
  if (!tracks.value.length) return;
  const nextIndex =
    loopMode.value === "shuffle"
      ? (player.currentIndex + 2) % tracks.value.length
      : (player.currentIndex + 1) % tracks.value.length;
  playTrack(nextIndex);
}

function cycleLoopMode() {
  const currentIndex = loopModes.findIndex((item) => item.key === loopMode.value);
  const nextIndex = (currentIndex + 1) % loopModes.length;
  loopMode.value = loopModes[nextIndex].key;
}

function showDrawer(mode = drawerMode.value) {
  drawerMode.value = mode;
  playlistDrawerOpen.value = true;
}

function recordHistory(track) {
  if (!track) return;
  const playedAt = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  playHistory.value = [
    { ...track, playedAt },
    ...playHistory.value.filter((item) => item.id !== track.id),
  ].slice(0, 12);
}

function formatTime(value) {
  const total = Math.max(0, Math.round(Number(value) || 0));
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

onMounted(refreshPlaylist);
</script>

<template>
  <section class="music-studio">
    <div class="side-actions" aria-label="播放器工具">
      <button type="button" title="刷新" aria-label="刷新" @click="refreshPlaylist">
        <RefreshCw :size="17" />
      </button>
      <button
        type="button"
        :title="player.isStreaming ? '停止生成试听' : '生成试听'"
        :aria-label="player.isStreaming ? '停止生成试听' : '生成试听'"
        @click="startStreamPreview"
      >
        <Square v-if="player.isStreaming" :size="17" />
        <Radio v-else :size="17" />
      </button>
      <label class="import-button" title="导入" aria-label="导入">
        <Upload :size="17" />
        <input accept="audio/*" type="file" @change="onImportFile" />
      </label>
      <button type="button" title="播放队列" aria-label="播放队列" @click="showDrawer('queue')">
        <ListMusic :size="17" />
      </button>
      <button type="button" title="播放历史" aria-label="播放历史" @click="showDrawer('history')">
        <History :size="17" />
      </button>
    </div>

    <p v-if="error" class="error-message">{{ error }}</p>

    <article class="player-stage minimal-player">
      <div class="stage-glow"></div>
      <div class="visual-core">
        <div class="waveform-rail hero-wave" aria-hidden="true">
          <i
            v-for="(height, index) in waveBars"
            :key="`wave-${index}`"
            :style="{ '--bar-height': `${height}%`, '--bar-delay': `${index * 30}ms` }"
          ></i>
        </div>

        <div :class="['turntable', { spinning: player.isPlaying }]">
          <div class="record-disc">
            <span class="record-ring outer"></span>
            <span class="record-ring inner"></span>
            <span class="record-label"><Disc3 :size="30" /></span>
          </div>
          <div class="tonearm"></div>
        </div>
      </div>

      <div class="progress-panel">
        <div class="progress-copy">
          <span>{{ formatTime(elapsedSeconds) }}</span>
          <span>{{ totalSeconds ? formatTime(totalSeconds) : "--:--" }}</span>
        </div>
        <div class="progress-track" aria-label="播放进度">
          <span :style="{ width: `${progressPercent}%` }"></span>
        </div>
      </div>

      <div class="transport-bar">
        <div class="track-summary">
          <strong>{{ currentTrack?.title || "暂无歌曲" }}</strong>
          <small>{{ currentTrack?.artist || "从播放列表选择一首歌" }}</small>
        </div>
        <div class="compact-controls" aria-label="播放器控制">
          <button class="icon-button" type="button" :disabled="!tracks.length" title="上一首" @click="previousTrack">
            <SkipBack :size="19" />
          </button>
          <button class="primary-play" type="button" :disabled="!currentTrack" @click="togglePlay">
            <Pause v-if="player.isPlaying" :size="24" />
            <Play v-else :size="24" />
            <span>{{ player.isPlaying ? "暂停" : "播放" }}</span>
          </button>
          <button class="icon-button" type="button" :disabled="!tracks.length" title="下一首" @click="nextTrack">
            <SkipForward :size="19" />
          </button>
          <button class="mode-button" type="button" title="播放模式" aria-label="播放模式" @click="cycleLoopMode">
            <component :is="activeLoopMode.icon" :size="19" />
            <span>{{ activeLoopMode.label }}</span>
          </button>
          <button class="icon-button" type="button" title="播放列表" aria-label="播放列表" @click="showDrawer('queue')">
            <ListMusic :size="19" />
          </button>
        </div>
      </div>
    </article>

    <aside :class="['drawer-panel', { open: playlistDrawerOpen }]" aria-label="播放列表与历史">
      <header class="drawer-header">
        <button class="drawer-collapse" type="button" title="收起" @click="playlistDrawerOpen = false">
          <X :size="18" />
        </button>
        <div>
          <p>播放管理</p>
          <h2>{{ drawerMode === "history" ? "播放历史" : "播放列表" }}</h2>
        </div>
      </header>

      <div class="drawer-tabs" role="tablist" aria-label="播放列表切换">
        <button
          :class="['drawer-tab', { active: drawerMode === 'queue' }]"
          type="button"
          @click="drawerMode = 'queue'"
        >
          <ListMusic :size="16" /> 播放列表
        </button>
        <button
          :class="['drawer-tab', { active: drawerMode === 'history' }]"
          type="button"
          @click="drawerMode = 'history'"
        >
          <History :size="16" /> 播放历史
        </button>
      </div>

      <div class="drawer-list">
        <button
          v-for="(track, index) in drawerTracks"
          :key="`${drawerMode}-${track.id}-${index}`"
          :class="['drawer-row', { active: currentTrack?.id === track.id }]"
          type="button"
          @click="playDrawerTrack(track, index)"
        >
          <span>{{ String(index + 1).padStart(2, "0") }}</span>
          <strong>{{ track.title }}</strong>
          <small>{{ drawerMode === "history" ? track.playedAt : track.artist }}</small>
        </button>
        <p v-if="!drawerTracks.length" class="empty-state">
          {{ drawerMode === "history" ? "暂无播放历史" : "暂无歌曲" }}
        </p>
      </div>
    </aside>

  </section>
</template>

<style scoped>
.music-studio {
  background:
    radial-gradient(circle at 50% 42%, rgba(34, 211, 238, 0.14), transparent 32%),
    linear-gradient(150deg, #071426, #040b15 72%);
  color: var(--color-text);
  height: 100%;
  overflow: hidden;
  padding: 24px 28px;
  position: relative;
}

.drawer-header p {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 800;
  margin: 0;
}

.drawer-header h2 {
  color: var(--color-heading);
  font-size: 24px;
  line-height: 1.05;
  margin: 0;
}

.side-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 7;
}

.side-actions button,
.import-button,
.icon-button,
.mode-button,
.drawer-collapse {
  align-items: center;
  background: rgba(9, 25, 43, 0.58);
  border: 1px solid rgba(125, 211, 252, 0.14);
  border-radius: 8px;
  color: var(--color-heading);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-weight: 850;
  justify-content: center;
}

.side-actions button,
.import-button {
  height: 40px;
  width: 40px;
}

.import-button input {
  display: none;
}

.player-stage {
  --stage-x-pad: clamp(24px, 4vw, 56px);

  align-content: center;
  display: grid;
  gap: 24px;
  grid-template-rows: minmax(300px, 1fr) max-content max-content;
  inset: 20px 86px 22px 28px;
  overflow: hidden;
  padding: 34px var(--stage-x-pad);
  position: absolute;
}

.minimal-player {
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.stage-glow {
  background: radial-gradient(circle at 50% 44%, rgba(34, 211, 238, 0.12), transparent 44%);
  inset: 0;
  pointer-events: none;
  position: absolute;
}

.visual-core {
  align-items: center;
  display: grid;
  isolation: isolate;
  justify-items: center;
  min-height: 0;
  position: relative;
  z-index: 1;
}

.waveform-rail {
  align-items: center;
  display: flex;
  gap: clamp(5px, 0.55vw, 9px);
  justify-content: center;
  overflow: hidden;
}

.hero-wave {
  -webkit-mask-image: radial-gradient(ellipse at center, #000 42%, rgba(0, 0, 0, 0.72) 66%, transparent 100%);
  background: transparent;
  border: 0;
  border-radius: 0;
  height: clamp(250px, 44vh, 430px);
  mask-image: radial-gradient(ellipse at center, #000 42%, rgba(0, 0, 0, 0.72) 66%, transparent 100%);
  max-width: 1040px;
  padding: 38px clamp(22px, 5vw, 72px);
  position: relative;
  width: min(76vw, 1120px);
}

.hero-wave::before {
  background:
    radial-gradient(ellipse at center, rgba(34, 211, 238, 0.12), rgba(8, 47, 73, 0.05) 44%, transparent 72%),
    repeating-linear-gradient(90deg, rgba(125, 211, 252, 0.04) 0 1px, transparent 1px 23px);
  content: "";
  inset: 0;
  pointer-events: none;
  position: absolute;
}

.waveform-rail i {
  animation: waveBreath 1.8s ease-in-out infinite;
  animation-delay: var(--bar-delay);
  background: linear-gradient(180deg, rgba(34, 211, 238, 0.96), rgba(52, 211, 153, 0.32));
  border-radius: 999px;
  display: block;
  height: var(--bar-height);
  min-height: 26px;
  opacity: 0.82;
  position: relative;
  width: clamp(7px, 0.58vw, 11px);
  z-index: 1;
}

.turntable {
  align-items: center;
  aspect-ratio: 1;
  background: radial-gradient(circle at 50% 48%, rgba(20, 184, 166, 0.18), rgba(4, 11, 21, 0.72) 62%);
  border: 1px solid rgba(125, 211, 252, 0.12);
  border-radius: 50%;
  box-shadow: 0 20px 60px rgba(0, 8, 20, 0.38), inset 0 0 0 1px rgba(255, 255, 255, 0.035);
  display: grid;
  justify-items: center;
  max-width: 300px;
  min-width: 210px;
  padding: 24px;
  position: absolute;
  right: max(4vw, 42px);
  width: 23vw;
  z-index: 2;
}

.record-disc {
  align-items: center;
  aspect-ratio: 1;
  background:
    radial-gradient(circle at center, #123955 0 9%, #071426 10% 26%, #0c1e33 27% 28%, #050b14 29% 100%);
  border: 1px solid rgba(125, 211, 252, 0.2);
  border-radius: 50%;
  display: grid;
  justify-items: center;
  position: relative;
  width: 82%;
}

.turntable.spinning .record-disc {
  animation: recordSpin 9s linear infinite;
}

.record-ring {
  border: 1px solid rgba(138, 164, 189, 0.16);
  border-radius: 50%;
  position: absolute;
}

.record-ring.outer {
  inset: 17%;
}

.record-ring.inner {
  inset: 34%;
}

.record-label {
  align-items: center;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.38), rgba(52, 211, 153, 0.22));
  border-radius: 50%;
  color: var(--color-heading);
  display: inline-flex;
  height: 64px;
  justify-content: center;
  width: 64px;
}

.tonearm {
  background: linear-gradient(180deg, rgba(216, 231, 245, 0.62), rgba(125, 211, 252, 0.18));
  border-radius: 999px;
  height: 45%;
  position: absolute;
  right: 23%;
  top: 14%;
  transform: rotate(30deg);
  transform-origin: top center;
  width: 7px;
}

.progress-panel {
  display: grid;
  gap: 10px;
  justify-self: stretch;
  margin-inline: calc(0px - var(--stage-x-pad));
  max-width: none;
  position: relative;
  width: calc(100% + var(--stage-x-pad) + var(--stage-x-pad));
  z-index: 1;
}

.progress-copy {
  align-items: center;
  color: var(--color-muted);
  display: flex;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  justify-content: space-between;
  padding-inline: var(--stage-x-pad);
}

.progress-track {
  background: rgba(138, 164, 189, 0.16);
  border-radius: 999px;
  height: 9px;
  overflow: hidden;
}

.progress-track span {
  background: linear-gradient(90deg, var(--color-brand-cyan), var(--color-brand-green));
  border-radius: inherit;
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.35);
  display: block;
  height: 100%;
}

.transport-bar {
  align-items: center;
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(220px, 1fr) max-content;
  position: relative;
  z-index: 1;
}

.track-summary {
  display: grid;
  gap: 4px;
  min-width: 0;
  text-align: left;
}

.track-summary strong {
  color: var(--color-heading);
  font-size: clamp(24px, 2.6vw, 38px);
  letter-spacing: 0;
  line-height: 1.05;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track-summary small {
  color: var(--color-muted-strong);
  font-size: 14px;
  font-weight: 780;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact-controls {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: center;
  position: relative;
  z-index: 1;
}

.icon-button {
  height: 44px;
  width: 44px;
}

.primary-play {
  align-items: center;
  background: linear-gradient(135deg, var(--color-accent-strong), #0f766e);
  border: 0;
  border-radius: 8px;
  color: var(--color-heading);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-weight: 900;
  gap: 8px;
  justify-content: center;
  min-height: 50px;
  min-width: 126px;
  padding: 0 22px;
}

.mode-button {
  gap: 8px;
  height: 44px;
  min-width: 126px;
  padding: 0 12px;
}

.mode-button span {
  color: var(--color-muted-strong);
  font-size: 13px;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.44;
}

.drawer-panel {
  background: linear-gradient(180deg, #102b43 0%, #071426 100%);
  border-left: 1px solid rgba(125, 211, 252, 0.14);
  bottom: 0;
  box-shadow: -24px 0 54px rgba(0, 8, 20, 0.3);
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  max-width: min(386px, calc(100vw - 84px));
  padding: 20px;
  position: absolute;
  right: 0;
  top: 0;
  transform: translateX(calc(100% + 18px));
  transition: transform 180ms ease;
  width: 386px;
  z-index: 8;
}

.drawer-panel.open {
  transform: translateX(0);
}

.drawer-header {
  align-items: start;
  display: grid;
  gap: 12px;
  grid-template-columns: 36px minmax(0, 1fr);
  margin-bottom: 16px;
}

.drawer-collapse {
  height: 36px;
  width: 36px;
}

.drawer-tabs {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 16px;
}

.drawer-tab {
  align-items: center;
  background: rgba(4, 16, 31, 0.54);
  border: 1px solid rgba(125, 211, 252, 0.12);
  border-radius: 8px;
  color: var(--color-muted-strong);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-size: 13px;
  font-weight: 850;
  gap: 7px;
  justify-content: center;
  min-height: 38px;
}

.drawer-tab.active {
  background: rgba(14, 165, 233, 0.22);
  border-color: rgba(34, 211, 238, 0.36);
  color: var(--color-heading);
}

.drawer-list {
  display: grid;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.drawer-row {
  background: rgba(4, 16, 31, 0.44);
  border: 1px solid rgba(125, 211, 252, 0.1);
  border-radius: 8px;
  color: var(--color-text);
  cursor: pointer;
  display: grid;
  font: inherit;
  gap: 4px 10px;
  grid-template-columns: 38px minmax(0, 1fr);
  min-height: 58px;
  padding: 10px;
  text-align: left;
}

.drawer-row:hover,
.drawer-row:focus-visible,
.drawer-row.active {
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.18), rgba(20, 184, 166, 0.08));
  border-color: rgba(34, 211, 238, 0.28);
  outline: none;
}

.drawer-row span {
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  grid-row: span 2;
}

.drawer-row strong {
  color: var(--color-heading);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-row small {
  color: var(--color-muted);
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
  border: 1px dashed rgba(125, 211, 252, 0.22);
  color: var(--color-muted);
}

.error-message {
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
  left: 28px;
  position: absolute;
  right: 86px;
  top: 20px;
  z-index: 5;
}

@keyframes recordSpin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes waveBreath {
  0%,
  100% {
    transform: scaleY(0.68);
  }
  50% {
    transform: scaleY(1.08);
  }
}

@media (max-width: 960px) {
  .player-stage {
    --stage-x-pad: 24px;

    inset: 18px 68px 20px 20px;
    padding: 24px;
  }

  .hero-wave {
    width: min(82vw, 760px);
  }

  .turntable {
    max-width: 240px;
    min-width: 180px;
    right: 24px;
  }

  .side-actions {
    right: 10px;
  }

}

@media (max-width: 720px) {
  .music-studio {
    padding: 16px;
  }

  .player-stage {
    inset: 18px 16px 18px;
  }

  .visual-core {
    align-content: center;
    gap: 16px;
  }

  .turntable {
    position: relative;
    right: auto;
    width: min(58vw, 220px);
  }

  .hero-wave {
    height: 220px;
    width: 100%;
  }

  .side-actions {
    flex-direction: row;
    right: 16px;
    top: 16px;
    transform: none;
  }

  .compact-controls {
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .transport-bar {
    align-items: start;
    grid-template-columns: 1fr;
  }

  .drawer-panel {
    max-width: calc(100vw - 69px);
    width: calc(100vw - 69px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .record-disc,
  .waveform-rail i {
    animation: none !important;
  }
}
</style>
