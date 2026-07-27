<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  History,
  ListMusic,
  Radio,
  RotateCcw,
  Square,
  Trash2,
  Upload,
  X,
} from "@lucide/vue";
import MusicPlaybackBackdrop from "../components/MusicPlaybackBackdrop.vue";
import MusicImportDrawer from "../components/MusicImportDrawer.vue";
import YtsAudioPlayer from "../components/YtsAudioPlayer.vue";
import { usePlayerStore } from "../stores/player";
import { usePlaylistStore } from "../stores/playlist";
import { useEnvironmentStore } from "../stores/environment";
import { loadSongObjectUrl } from "../services/music";
import { apiBase, selectedApiTarget } from "../services/http";

const player = usePlayerStore();
const playlist = usePlaylistStore();
const environment = useEnvironmentStore();
const error = ref("");
const streamPrompt = ref("夏夜骑行的轻快电子乐");
const playlistDrawerOpen = ref(false);
const importDrawerOpen = ref(false);
const drawerMode = ref("queue");
const loopMode = ref("queue");
const playHistory = ref([]);
const trackUrlByHash = ref(new Map());
const resumeSeekTime = ref(null);
let renditionRefreshTimer = null;

const PLAYBACK_RESUME_STORAGE_KEY = "yts-music-playback-state";
const RENDITION_REFRESH_DELAY_MS = 1500;

const loopModes = [
  { key: "queue", label: "循环播放" },
  { key: "single", label: "单曲循环" },
  { key: "shuffle", label: "随机播放" },
];

const tracks = computed(() =>
  playlist.activeItems.map((item) => ({
    id: item.id,
    title: item.title_alias || "未命名歌曲",
    artist: item.artist_alias || "未知艺人",
    contentHash: item.content_hash,
    metaSong: item.meta_song,
    playbackStatus: item.playback_status,
    playbackErrorCode: item.playback_error_code,
    playbackErrorMessage: item.playback_error_message,
    url: playableTrackUrl(item),
  })),
);

const deletedTracks = computed(() =>
  playlist.deletedItems.map((item) => ({
    id: item.id,
    title: item.title_alias || "未命名歌曲",
    artist: item.artist_alias || "未知艺人",
    contentHash: item.content_hash,
    metaSong: item.meta_song,
    deletedAt: item.deleted_at_ms,
    deletedAtLabel: formatDeletedAt(item.deleted_at_ms),
  })),
);

const currentTrack = computed(() => player.currentTrack || tracks.value[0] || null);
const activeLoopMode = computed(() => loopModes.find((item) => item.key === loopMode.value) || loopModes[0]);
const drawerTracks = computed(() => {
  if (drawerMode.value === "history") return playHistory.value;
  if (drawerMode.value === "deleted") return deletedTracks.value;
  return tracks.value;
});
const drawerTitle = computed(() => {
  if (drawerMode.value === "history") return "播放历史";
  if (drawerMode.value === "deleted") return "删除历史";
  return "播放列表";
});
const drawerEmptyText = computed(() => {
  if (drawerMode.value === "history") return "暂无播放历史";
  if (drawerMode.value === "deleted") return "暂无删除历史";
  return "暂无歌曲";
});

function playableTrackUrl(item) {
  if (!item.content_hash) {
    throw new Error("playlist item requires content_hash");
  }
  return trackUrlByHash.value.get(item.content_hash) || "";
}

async function refreshPlaylist() {
  error.value = "";
  try {
    await playlist.hydrate({ scope: environment.target });
    await loadPlayableTrackUrls(playlist.activeItems);
    player.setQueue(tracks.value);
    restorePlaybackResumeState();
    scheduleRenditionRefresh();
  } catch (err) {
    error.value = formatMusicLoadError(err);
  }
}

async function loadPlayableTrackUrls(items) {
  const previousUrls = trackUrlByHash.value;
  const nextUrls = new Map();
  const createdUrls = [];
  try {
    for (const item of items) {
      if (!item.content_hash) {
        throw new Error("playlist item requires content_hash");
      }
      if (item.playback_status !== "ready") continue;
      const existingUrl = previousUrls.get(item.content_hash);
      if (existingUrl) {
        nextUrls.set(item.content_hash, existingUrl);
        continue;
      }
      const objectUrl = await loadSongObjectUrl({
        contentHash: item.content_hash,
        target: environment.target,
      });
      createdUrls.push(objectUrl);
      nextUrls.set(item.content_hash, objectUrl);
    }
  } catch (err) {
    revokePlayableTrackUrls(createdUrls);
    throw err;
  }
  for (const [contentHash, objectUrl] of previousUrls) {
    if (!nextUrls.has(contentHash)) {
      URL.revokeObjectURL(objectUrl);
    }
  }
  trackUrlByHash.value = nextUrls;
}

function scheduleRenditionRefresh() {
  if (renditionRefreshTimer != null) {
    clearTimeout(renditionRefreshTimer);
    renditionRefreshTimer = null;
  }
  const hasUnfinishedRendition = playlist.activeItems.some(
    (item) => item.playback_status === "pending" || item.playback_status === "processing",
  );
  if (!hasUnfinishedRendition) return;
  renditionRefreshTimer = setTimeout(async () => {
    renditionRefreshTimer = null;
    await refreshPlaylist();
  }, RENDITION_REFRESH_DELAY_MS);
}

function revokePlayableTrackUrls(urls = trackUrlByHash.value) {
  for (const objectUrl of urls instanceof Map ? urls.values() : urls) {
    URL.revokeObjectURL(objectUrl);
  }
}

function formatMusicLoadError(err) {
  const rawMessage = err instanceof Error ? err.message : String(err);
  const endpoint = err?.path ? `，接口 ${err.path}` : "";
  const targetBase = apiBase(environment.target);
  const status = err?.status ? `，状态 ${err.status}` : "";
  if (err?.status === 404) {
    return `播放列表加载失败：当前环境 ${environment.target} (${targetBase}) 未提供音乐接口${endpoint}，不是播放器布局错误。原始错误：${rawMessage}`;
  }
  if (rawMessage === "Failed to fetch") {
    return `播放列表加载失败：无法连接当前环境 ${environment.target} (${targetBase})${endpoint}。请确认后端服务已启动。原始错误：${rawMessage}`;
  }
  return `播放列表加载失败：当前环境 ${environment.target} (${targetBase})${endpoint}${status}。原始错误：${rawMessage}`;
}

function normalizePlaybackResumeTime(value) {
  const normalizedTime = Number(value);
  if (!Number.isFinite(normalizedTime) || normalizedTime < 0) {
    throw new Error("音乐播放进度记录的 currentTime 必须是非负数字");
  }
  return normalizedTime;
}

function readPlaybackResumeState() {
  const rawState = localStorage.getItem(PLAYBACK_RESUME_STORAGE_KEY);
  if (!rawState) return null;
  const parsedState = JSON.parse(rawState);
  if (!parsedState || typeof parsedState !== "object" || Array.isArray(parsedState)) {
    throw new Error("音乐播放进度记录必须是对象");
  }
  if (typeof parsedState.target !== "string" || !parsedState.target) {
    throw new Error("音乐播放进度记录缺少 target");
  }
  if (typeof parsedState.trackId !== "string" || !parsedState.trackId) {
    throw new Error("音乐播放进度记录缺少 trackId");
  }
  if (typeof parsedState.contentHash !== "string" || !parsedState.contentHash) {
    throw new Error("音乐播放进度记录缺少 contentHash");
  }
  return {
    target: parsedState.target,
    trackId: parsedState.trackId,
    contentHash: parsedState.contentHash,
    currentTime: normalizePlaybackResumeTime(parsedState.currentTime),
  };
}

function writePlaybackResumeState(track, currentTime) {
  if (!track) return;
  if (!track.id) {
    throw new Error("播放进度记录需要歌曲 id");
  }
  if (!track.contentHash) {
    throw new Error("播放进度记录需要歌曲 contentHash");
  }
  const normalizedTime = normalizePlaybackResumeTime(currentTime);
  localStorage.setItem(
    PLAYBACK_RESUME_STORAGE_KEY,
    JSON.stringify({
      target: environment.target,
      trackId: track.id,
      contentHash: track.contentHash,
      currentTime: normalizedTime,
      updatedAt: Date.now(),
    }),
  );
}

function restorePlaybackResumeState() {
  resumeSeekTime.value = null;
  const resumeState = readPlaybackResumeState();
  if (!resumeState) return;
  if (resumeState.target !== environment.target) return;
  const resumeIndex = tracks.value.findIndex(
    (track) => track.id === resumeState.trackId || track.contentHash === resumeState.contentHash,
  );
  if (resumeIndex < 0) return;
  player.selectAt(resumeIndex, { currentTime: resumeState.currentTime, isPlaying: false });
  resumeSeekTime.value = resumeState.currentTime;
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

function playTrack(index) {
  error.value = "";
  try {
    if (tracks.value[index]?.playbackStatus !== "ready") {
      throw new Error("歌曲播放版本尚未就绪");
    }
    resumeSeekTime.value = null;
    player.playAt(index);
    recordHistory(tracks.value[index]);
    writePlaybackResumeState(tracks.value[index], 0);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function playDrawerTrack(track, index) {
  if (drawerMode.value === "deleted") return;
  const targetIndex = drawerMode.value === "history" ? tracks.value.findIndex((item) => item.id === track.id) : index;
  if (targetIndex >= 0) playTrack(targetIndex);
}

async function handleDeletePlaylistItem(track) {
  error.value = "";
  try {
    if (!track?.id) throw new Error("删除播放列表歌曲需要 item id");
    await playlist.deleteItem(track.id);
    await loadPlayableTrackUrls(playlist.activeItems);
    player.setQueue(tracks.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function handleRestorePlaylistItem(track) {
  error.value = "";
  try {
    if (!track?.id) throw new Error("恢复播放列表歌曲需要 item id");
    await playlist.restoreItem(track.id);
    await loadPlayableTrackUrls(playlist.activeItems);
    player.setQueue(tracks.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function drawerTrackMeta(track) {
  if (drawerMode.value === "history") return track.playedAt;
  if (drawerMode.value === "deleted") return track.deletedAtLabel;
  if (track.playbackStatus === "pending" || track.playbackStatus === "processing") {
    return "处理中";
  }
  if (track.playbackStatus === "failed") {
    return track.playbackErrorMessage || "转码失败";
  }
  return track.artist;
}

async function handleRetryRendition(track) {
  error.value = "";
  try {
    if (track?.playbackStatus !== "failed") {
      throw new Error("只有转码失败的歌曲可以重试");
    }
    await playlist.retryRendition(track.contentHash);
    await loadPlayableTrackUrls(playlist.activeItems);
    player.setQueue(tracks.value);
    scheduleRenditionRefresh();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function formatDeletedAt(value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp)) {
    throw new Error("删除历史歌曲需要 deleted_at_ms");
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    throw new Error("删除历史歌曲的 deleted_at_ms 无法解析");
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
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

function handleAudioPlay() {
  player.setPlaying(true);
  recordHistory(currentTrack.value);
  writePlaybackResumeState(currentTrack.value, player.currentTime);
}

function handleAudioPause() {
  player.setPlaying(false);
  writePlaybackResumeState(currentTrack.value, player.currentTime);
}

function handleAudioEnded() {
  if (loopMode.value === "single") return;
  if (loopMode.value === "queue" && tracks.value.length === 1) return;
  if (tracks.value.length > 1) {
    nextTrack();
  } else {
    player.setPlaying(false);
    writePlaybackResumeState(currentTrack.value, player.duration > 0 ? player.duration : player.currentTime);
  }
}

function handleTimeUpdate(currentTime) {
  player.setPlaybackClock({ currentTime });
  writePlaybackResumeState(currentTrack.value, currentTime);
}

function handleDurationChange(duration) {
  player.setPlaybackClock({ duration });
}

function handleSeekApplied(currentTime) {
  resumeSeekTime.value = null;
  player.setPlaybackClock({ currentTime });
  writePlaybackResumeState(currentTrack.value, currentTime);
}

function handleAudioError(message) {
  error.value = message;
  player.setPlaying(false);
}

function recordHistory(track) {
  if (!track) return;
  const playedAt = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  playHistory.value = [
    { ...track, playedAt },
    ...playHistory.value.filter((item) => item.id !== track.id),
  ].slice(0, 12);
}

watch(
  () => environment.target,
  async (nextTarget, previousTarget) => {
    if (nextTarget === previousTarget) return;
    if (renditionRefreshTimer != null) {
      clearTimeout(renditionRefreshTimer);
      renditionRefreshTimer = null;
    }
    await refreshPlaylist();
  },
);

// 本地服务是惰性启动的(见 stores/environment.js),首次挂载时大概率还没就绪;一旦健康检查
// 转为 online 就自动重试一次,而不需要用户手动刷新页面。
watch(
  () => environment.targetHealth(environment.target),
  async (status) => {
    if (status === "online" && error.value) await refreshPlaylist();
  },
);

onMounted(async () => {
  environment.attach();
  await refreshPlaylist();
});

onBeforeUnmount(() => {
  writePlaybackResumeState(currentTrack.value, player.currentTime);
  environment.detach();
  player.setQueue([]);
  if (renditionRefreshTimer != null) clearTimeout(renditionRefreshTimer);
  revokePlayableTrackUrls();
});
</script>

<template>
  <section class="music-studio">
    <div class="side-actions" aria-label="播放器工具">
      <button
        type="button"
        :title="player.isStreaming ? '停止生成试听' : '生成试听'"
        :aria-label="player.isStreaming ? '停止生成试听' : '生成试听'"
        @click="startStreamPreview"
      >
        <Square v-if="player.isStreaming" :size="17" />
        <Radio v-else :size="17" />
      </button>
      <button type="button" title="导入" aria-label="导入" @click="importDrawerOpen = true">
        <Upload :size="17" />
      </button>
      <button type="button" title="播放队列" aria-label="播放队列" @click="showDrawer('queue')">
        <ListMusic :size="17" />
      </button>
      <button type="button" title="播放历史" aria-label="播放历史" @click="showDrawer('history')">
        <History :size="17" />
      </button>
    </div>

    <p v-if="error" class="error-message">{{ error }}</p>

    <Teleport to="#music-nav-playback-target">
      <MusicPlaybackBackdrop
        class="music-nav-playback"
        :playing="player.isPlaying"
      />
    </Teleport>

    <article class="player-stage minimal-player">
      <div class="stage-glow"></div>
      <YtsAudioPlayer
        class="player-surface"
        :loop-label="activeLoopMode.label"
        :loop-mode="loopMode"
        :playing="player.isPlaying"
        :repeat-current="loopMode === 'queue' && tracks.length === 1"
        :seek-time="resumeSeekTime"
        :track="currentTrack"
        @cycle-loop="cycleLoopMode"
        @duration-change="handleDurationChange"
        @ended="handleAudioEnded"
        @next="nextTrack"
        @pause="handleAudioPause"
        @play="handleAudioPlay"
        @play-error="handleAudioError"
        @previous="previousTrack"
        @seek-applied="handleSeekApplied"
        @time-update="handleTimeUpdate"
      />
    </article>

    <MusicImportDrawer
      :open="importDrawerOpen"
      :target="environment.target"
      @close="importDrawerOpen = false"
      @imported="refreshPlaylist"
    />

    <div v-if="playlistDrawerOpen" class="drawer-layer" role="presentation">
      <button
        class="drawer-scrim"
        type="button"
        aria-label="关闭播放列表面板"
        @click="playlistDrawerOpen = false"
      ></button>
      <aside class="drawer-panel open" aria-label="播放列表与历史">
        <header class="drawer-header">
          <div class="drawer-title">
            <span><ListMusic :size="18" /></span>
            <div>
              <p>播放管理</p>
              <h2>{{ drawerTitle }}</h2>
            </div>
          </div>
          <button class="drawer-collapse" type="button" title="关闭" @click="playlistDrawerOpen = false">
            <X :size="18" />
          </button>
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
          <button
            :class="['drawer-tab', { active: drawerMode === 'deleted' }]"
            type="button"
            @click="drawerMode = 'deleted'"
          >
            <Trash2 :size="16" /> 删除历史
          </button>
        </div>

        <div class="drawer-list">
          <article
            v-for="(track, index) in drawerTracks"
            :key="`${drawerMode}-${track.id}-${index}`"
            :class="['drawer-row', { active: currentTrack?.id === track.id && drawerMode !== 'deleted' }]"
          >
            <button
              class="drawer-row-main"
              type="button"
              :disabled='drawerMode === "deleted" || track.playbackStatus !== "ready"'
              @click="playDrawerTrack(track, index)"
            >
              <span class="drawer-row-index">{{ String(index + 1).padStart(2, "0") }}</span>
              <strong>{{ track.title }}</strong>
              <small>{{ drawerTrackMeta(track) }}</small>
            </button>
            <button
              v-if="drawerMode === 'queue' && track.playbackStatus === 'failed'"
              class="drawer-row-action retry"
              type="button"
              title="重试转码"
              aria-label="重试转码"
              @click.stop="handleRetryRendition(track)"
            >
              <RotateCcw :size="13" />
              <span>重试</span>
            </button>
            <button
              v-if="drawerMode === 'queue'"
              class="drawer-row-action danger"
              type="button"
              title="移除"
              aria-label="移除歌曲"
              @click.stop="handleDeletePlaylistItem(track)"
            >
              <Trash2 :size="13" />
              <span>移除</span>
            </button>
            <button
              v-else-if="drawerMode === 'deleted'"
              class="drawer-row-action restore"
              type="button"
              title="恢复"
              aria-label="恢复歌曲"
              @click.stop="handleRestorePlaylistItem(track)"
            >
              <RotateCcw :size="13" />
              <span>恢复</span>
            </button>
          </article>
          <p v-if="!drawerTracks.length" class="empty-state">
            {{ drawerEmptyText }}
          </p>
        </div>
      </aside>
    </div>

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
.import-button {
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
  --shell-sidebar-width: 69px;
  --stage-left-inset: 28px;
  --stage-x-pad: clamp(24px, 4vw, 56px);

  align-content: end;
  display: grid;
  gap: 24px;
  grid-template-rows: auto;
  inset: 20px 86px 22px 28px;
  overflow: visible;
  padding: 34px var(--stage-x-pad);
  position: absolute;
  z-index: 1;
}

.music-nav-playback {
  z-index: 0;
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

.player-surface {
  min-height: 0;
}

.drawer-layer {
  inset: 0;
  pointer-events: none;
  position: fixed;
  z-index: 8;
}

.drawer-scrim {
  background: rgba(2, 8, 18, 0.24);
  border: 0;
  cursor: pointer;
  inset: 0;
  pointer-events: auto;
  position: absolute;
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
  pointer-events: auto;
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
  display: flex;
  gap: 14px;
  justify-content: space-between;
  margin-bottom: 16px;
}

.drawer-title {
  align-items: center;
  display: grid;
  gap: 12px;
  grid-template-columns: 42px minmax(0, 1fr);
  min-width: 0;
}

.drawer-title > span {
  align-items: center;
  background: rgba(14, 165, 233, 0.22);
  border-radius: 8px;
  color: var(--color-brand-cyan);
  display: inline-flex;
  height: 42px;
  justify-content: center;
  width: 42px;
}

.drawer-collapse {
  align-items: center;
  background: rgba(9, 25, 43, 0.72);
  border: 0;
  border-radius: 8px;
  color: var(--color-heading);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  justify-content: center;
  height: 36px;
  width: 36px;
}

.drawer-tabs {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
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
  align-content: start;
  display: grid;
  gap: 4px;
  grid-auto-rows: max-content;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.drawer-row {
  background: rgba(4, 16, 31, 0.3);
  border: 0;
  border-radius: 6px;
  box-sizing: border-box;
  color: var(--color-text);
  cursor: pointer;
  display: grid;
  font: inherit;
  align-items: center;
  gap: 6px;
  grid-template-columns: 24px minmax(0, 1fr) minmax(48px, 78px);
  min-height: 34px;
  padding: 5px 8px;
  position: relative;
  text-align: left;
  width: 100%;
}

.drawer-row:has(.drawer-row-action) {
  padding-right: 60px;
}

.drawer-row:has(.drawer-row-action.retry) {
  padding-right: 112px;
}

.drawer-row:hover,
.drawer-row:focus-within,
.drawer-row.active {
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.18), rgba(20, 184, 166, 0.08));
  box-shadow: inset 2px 0 0 rgba(34, 211, 238, 0.42);
  outline: none;
}

.drawer-row-main {
  appearance: none;
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  display: contents;
  font: inherit;
  text-align: left;
}

.drawer-row-main:disabled {
  cursor: default;
}

.drawer-row span {
  color: var(--color-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.drawer-row strong {
  color: var(--color-heading);
  font-size: 12px;
  line-height: 1.1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-row small {
  color: var(--color-muted);
  font-size: 11px;
  justify-self: end;
  line-height: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-row-action {
  align-items: center;
  background: rgba(9, 25, 43, 0.72);
  border: 1px solid rgba(125, 211, 252, 0.14);
  border-radius: 6px;
  color: var(--color-heading);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-size: 11px;
  font-weight: 850;
  gap: 4px;
  justify-content: center;
  min-height: 24px;
  min-width: 48px;
  padding: 0 7px;
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
}

.drawer-row-action span {
  color: inherit;
  font-size: 11px;
}

.drawer-row-action.danger {
  color: #fecdd3;
}

.drawer-row-action.restore {
  color: #bbf7d0;
}

.drawer-row-action.retry {
  color: #fde68a;
  right: 58px;
}

.drawer-row-action:hover,
.drawer-row-action:focus-visible {
  background: rgba(14, 165, 233, 0.24);
  border-color: rgba(34, 211, 238, 0.34);
  outline: none;
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

@media (max-width: 960px) {
  .player-stage {
    --stage-left-inset: 20px;
    --stage-x-pad: 24px;

    inset: 18px 68px 20px 20px;
    padding: 24px;
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
    --stage-left-inset: 16px;

    inset: 18px 16px 18px;
  }

  .side-actions {
    flex-direction: row;
    right: 16px;
    top: 16px;
    transform: none;
  }

  .drawer-panel {
    max-width: calc(100vw - 69px);
    width: calc(100vw - 69px);
  }
}
</style>
