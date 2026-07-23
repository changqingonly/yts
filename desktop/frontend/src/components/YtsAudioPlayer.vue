<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Pause, Play, Repeat1, Repeat2, Shuffle, SkipBack, SkipForward, Volume2, VolumeX } from "@lucide/vue";

const props = defineProps({
  track: { type: Object, default: null },
  playing: { type: Boolean, default: false },
  seekTime: { type: Number, default: null },
  loopMode: { type: String, required: true },
  loopLabel: { type: String, required: true },
  repeatCurrent: { type: Boolean, default: false },
});

const emit = defineEmits([
  "play",
  "pause",
  "ended",
  "time-update",
  "duration-change",
  "previous",
  "next",
  "cycle-loop",
  "play-error",
  "seek-applied",
  "audio-ready",
]);

const audioRef = ref(null);
const currentTime = ref(0);
const duration = ref(0);
const mediaReady = ref(false);
const sourceLoadVersion = ref(0);
const loadingSource = ref(false);
const muted = ref(false);
const volume = ref(1);

const MEDIA_ERROR_MESSAGES = {
  1: "播放被中止",
  2: "网络连接失败或文件鉴权失败",
  3: "音频解码失败",
  4: "浏览器不支持该音频格式或服务端没有返回音频文件",
};

const sourceUrl = computed(() => props.track?.url || "");
const trackTitle = computed(() => props.track?.title || "暂无歌曲");
const trackArtist = computed(() => props.track?.artist || "从播放列表选择一首歌");
const currentTimeLabel = computed(() => formatTimelineTime(currentTime.value));
const durationLabel = computed(() => formatTimelineTime(duration.value));
const timelineProgressRatio = computed(() => {
  if (!Number.isFinite(duration.value) || duration.value <= 0) return 0;
  return Math.min(1, Math.max(0, currentTime.value / duration.value));
});
const timelineProgress = computed(() => `${timelineProgressRatio.value * 100}%`);
const timelineLabelPlacement = computed(() => {
  if (timelineProgressRatio.value <= 0.06) return "edge-start";
  if (timelineProgressRatio.value >= 0.94) return "edge-end";
  return "edge-middle";
});
const loopIcon = computed(() => {
  if (props.loopMode === "single") return Repeat1;
  if (props.loopMode === "shuffle") return Shuffle;
  return Repeat2;
});

function requireAudio() {
  if (!audioRef.value) {
    throw new Error("YtsAudioPlayer requires an audio element");
  }
  return audioRef.value;
}

function setCurrentTime(value) {
  currentTime.value = Math.max(0, Number(value) || 0);
  emit("time-update", currentTime.value);
}

function setDuration(value) {
  duration.value = Math.max(0, Number(value) || 0);
  emit("duration-change", duration.value);
}

function formatTimelineTime(value) {
  const safeValue = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(safeValue / 60);
  const seconds = Math.floor(safeValue % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function normalizedSeekTime() {
  if (props.seekTime == null) return null;
  const seekTime = Number(props.seekTime);
  if (!Number.isFinite(seekTime) || seekTime < 0) {
    throw new Error("YtsAudioPlayer seekTime must be a non-negative number");
  }
  if (duration.value > 0) return Math.min(seekTime, duration.value);
  return seekTime;
}

function sourceReadyForPlayback() {
  if (!sourceUrl.value) return false;
  return mediaReady.value && requireAudio().readyState >= 1;
}

async function applySeekTime() {
  if (!sourceReadyForPlayback()) return;
  const targetTime = normalizedSeekTime();
  if (targetTime == null) return;
  requireAudio().currentTime = targetTime;
  setCurrentTime(targetTime);
  emit("seek-applied", targetTime);
}

async function syncPlaybackIntent() {
  const player = requireAudio();
  const playLoadVersion = sourceLoadVersion.value;
  if (!sourceUrl.value) {
    player.pause();
    return;
  }
  if (!props.playing) {
    if (!player.paused) player.pause();
    return;
  }
  if (!sourceReadyForPlayback()) return;
  if (player.paused) {
    try {
      await player.play();
    } catch (err) {
      if (isPlayInterruptedBySourceLoad(err, playLoadVersion)) return;
      emit("play-error", formatPlaybackError(err));
    }
  }
}

function isPlayInterruptedBySourceLoad(err, playLoadVersion) {
  if (playLoadVersion === sourceLoadVersion.value) return false;
  if (typeof DOMException === "undefined" || !(err instanceof DOMException)) return false;
  return err.name === "AbortError" && err.message.includes("new load request");
}

function formatPlaybackError(err) {
  const mediaError = extractNativeMediaError(err);
  const code = typeof mediaError?.code === "number" ? mediaError.code : null;
  if (code != null) {
    const reason = MEDIA_ERROR_MESSAGES[code] || "未知媒体错误";
    return `音频加载失败：${reason}（MediaError ${code}）`;
  }
  if (err instanceof Error && err.message) {
    return `音频加载失败：${err.message}`;
  }
  if (typeof err === "string" && err.trim()) {
    return `音频加载失败：${err}`;
  }
  return "音频加载失败：无法读取音频文件";
}

function extractNativeMediaError(err) {
  const mediaError = err?.currentTarget?.error || err?.target?.error;
  if (mediaError) return mediaError;
  if (typeof err?.code === "number" && err.code >= 1 && err.code <= 4) return err;
  return null;
}

function handlePlay() {
  emit("play");
}

function handlePause() {
  if (loadingSource.value && props.playing) return;
  emit("pause");
}

function handleEnded() {
  emit("ended");
}

function handleTimeUpdate(event) {
  setCurrentTime(event.currentTarget.currentTime);
}

async function togglePlayback() {
  const player = requireAudio();
  if (!sourceUrl.value) return;
  if (!player.paused) {
    player.pause();
    return;
  }
  try {
    await player.play();
  } catch (err) {
    emit("play-error", formatPlaybackError(err));
  }
}

function handleSeekInput(event) {
  const nextTime = Number(event.currentTarget.value);
  if (!Number.isFinite(nextTime) || nextTime < 0) {
    throw new Error("播放进度必须是非负数字");
  }
  requireAudio().currentTime = nextTime;
  setCurrentTime(nextTime);
}

function handleVolumeInput(event) {
  const nextVolume = Number(event.currentTarget.value);
  if (!Number.isFinite(nextVolume) || nextVolume < 0 || nextVolume > 1) {
    throw new Error("播放音量必须在 0 到 1 之间");
  }
  const player = requireAudio();
  player.volume = nextVolume;
  player.muted = false;
  volume.value = nextVolume;
  muted.value = false;
}

function toggleMuted() {
  const player = requireAudio();
  player.muted = !player.muted;
  muted.value = player.muted;
}

async function handleLoadedMetadata(event) {
  loadingSource.value = false;
  mediaReady.value = true;
  setDuration(event.currentTarget.duration || 0);
  await applySeekTime();
  await syncPlaybackIntent();
}

function handleDurationChange(event) {
  setDuration(event.currentTarget.duration || 0);
}

function handleAudioElementError(event) {
  loadingSource.value = false;
  emit("play-error", formatPlaybackError(event));
}

onMounted(() => {
  emit("audio-ready", requireAudio());
});

onBeforeUnmount(() => {
  emit("audio-ready", null);
});

watch(sourceUrl, async (nextSourceUrl) => {
  sourceLoadVersion.value += 1;
  const loadVersion = sourceLoadVersion.value;
  loadingSource.value = true;
  mediaReady.value = false;
  currentTime.value = 0;
  duration.value = 0;
  try {
    await nextTick();
    if (loadVersion !== sourceLoadVersion.value) return;
    const player = requireAudio();
    if (nextSourceUrl) {
      player.src = nextSourceUrl;
      player.load();
    } else {
      player.removeAttribute("src");
      player.load();
      player.pause();
      loadingSource.value = false;
    }
  } catch (err) {
    if (loadVersion === sourceLoadVersion.value) {
      loadingSource.value = false;
    }
    emit("play-error", formatPlaybackError(err));
  }
});

watch(
  () => props.playing,
  async () => {
    await syncPlaybackIntent();
  },
);

watch(
  () => props.seekTime,
  async () => {
    try {
      await applySeekTime();
    } catch (err) {
      emit("play-error", formatPlaybackError(err));
    }
  },
);
</script>

<template>
  <section
    class="yts-audio-player"
    :class="{ empty: !sourceUrl, playing }"
    :style="{ '--timeline-progress': timelineProgress }"
  >
    <audio
      ref="audioRef"
      class="native-audio"
      :loop="repeatCurrent || loopMode === 'single'"
      preload="metadata"
      @durationchange="handleDurationChange"
      @ended="handleEnded"
      @error="handleAudioElementError"
      @loadedmetadata="handleLoadedMetadata"
      @pause="handlePause"
      @play="handlePlay"
      @timeupdate="handleTimeUpdate"
    ></audio>

    <div class="timeline-row" aria-label="播放进度">
      <div :class="['time-progress', timelineLabelPlacement]" aria-label="时间进度">
        {{ currentTimeLabel }}/{{ durationLabel }}
      </div>
      <input
        class="timeline-range"
        type="range"
        aria-label="seek"
        min="0"
        :max="duration || 0"
        step="0.1"
        :value="currentTime"
        :disabled="!sourceUrl || duration <= 0"
        @input="handleSeekInput"
      />
    </div>

    <div class="media-controls">
        <div class="control-row">
          <div class="track-summary">
            <strong>{{ trackTitle }}</strong>
            <small>{{ trackArtist }}</small>
          </div>
          <div class="button-groups">
            <div class="transport-group" aria-label="播放控制">
              <button
                class="transport-button"
                type="button"
                title="上一首"
                :disabled="!sourceUrl"
                @click="emit('previous')"
              >
                <SkipBack :size="18" />
              </button>
              <button
                class="transport-button primary"
                type="button"
                :title="playing ? '暂停' : '播放'"
                :aria-label="playing ? 'pause' : 'play'"
                :disabled="!sourceUrl"
                @click="togglePlayback"
              >
                <Pause v-if="playing" :size="20" />
                <Play v-else :size="20" />
              </button>
              <button
                class="transport-button"
                type="button"
                title="下一首"
                :disabled="!sourceUrl"
                @click="emit('next')"
              >
                <SkipForward :size="18" />
              </button>
            </div>
            <div class="utility-group" aria-label="声音与播放模式">
              <button
                class="volume-button"
                type="button"
                :title="muted ? '取消静音' : '静音'"
                :aria-label="muted ? 'unmute' : 'mute'"
                @click="toggleMuted"
              >
                <VolumeX v-if="muted || volume === 0" :size="18" />
                <Volume2 v-else :size="18" />
              </button>
              <input
                class="volume-range"
                type="range"
                aria-label="volume"
                min="0"
                max="1"
                step="0.05"
                :value="volume"
                @input="handleVolumeInput"
              />
              <button class="mode-button" type="button" title="播放模式" @click="emit('cycle-loop')">
                <component :is="loopIcon" :size="18" />
                <span>{{ loopLabel }}</span>
              </button>
            </div>
          </div>
        </div>
    </div>
  </section>
</template>

<style scoped>
.yts-audio-player {
  --media-accent-color: var(--color-brand-cyan);
  --media-background-color: transparent;
  --media-control-background: rgba(9, 25, 43, 0.52);
  --media-control-hover-background: rgba(14, 165, 233, 0.22);
  --media-primary-color: var(--color-heading);
  --media-secondary-color: rgba(138, 164, 189, 0.72);
  --media-text-color: var(--color-heading);
  --media-time-range-buffered-color: rgba(138, 164, 189, 0.18);
  --media-time-range-track-background: rgba(138, 164, 189, 0.14);

  display: grid;
  gap: clamp(18px, 3.2vh, 34px);
  grid-template-rows: auto auto;
  min-height: 0;
  min-width: 0;
  position: relative;
  z-index: 1;
}

.native-audio {
  position: absolute;
  visibility: hidden;
}

.media-controls {
  --media-control-bar-display: block;

  background: transparent;
  display: block;
  margin-inline: auto;
  max-width: none;
  min-width: 0;
}

.time-progress {
  color: rgba(216, 231, 245, 0.82);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  font-weight: 850;
  left: var(--timeline-progress);
  line-height: 1.2;
  min-height: 16px;
  pointer-events: none;
  position: absolute;
  text-align: center;
  top: 18px;
  transform: translate(-50%, -100%);
  white-space: nowrap;
  z-index: 2;
}

.time-progress.edge-start {
  left: 0;
  text-align: left;
  transform: translateY(-100%);
}

.time-progress.edge-end {
  left: auto;
  right: 0;
  text-align: right;
  transform: translateY(-100%);
}

.timeline-row {
  align-items: center;
  display: grid;
  gap: 0;
  grid-template-columns: minmax(0, 1fr);
  margin-left: calc(0px - var(--stage-x-pad, 0px) - var(--stage-left-inset));
  margin-right: 0;
  min-width: 0;
  padding-top: 22px;
  position: relative;
  width: calc(100vw - var(--shell-sidebar-width));
  z-index: 2;
}

.control-row {
  align-items: center;
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(180px, 1fr) max-content;
  min-width: 0;
}

.track-summary {
  display: grid;
  gap: 3px;
  justify-items: start;
  line-height: 1.2;
  min-width: 0;
  text-align: left;
}

.track-summary strong {
  color: var(--color-heading);
  font-size: 18px;
  letter-spacing: 0;
  line-height: 1.08;
  max-width: min(360px, 32vw);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track-summary small {
  color: var(--color-muted-strong);
  font-size: 13px;
  font-weight: 760;
  line-height: 1.2;
  max-width: min(360px, 32vw);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.button-groups {
  align-items: center;
  display: flex;
  gap: 14px;
  justify-content: end;
  min-width: 0;
}

.transport-group,
.utility-group {
  align-items: center;
  min-width: 0;
}

.transport-group,
.utility-group {
  display: flex;
  gap: 10px;
}

.timeline-group {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(48px, auto) minmax(0, 1fr) minmax(48px, auto);
}

.timeline-range {
  accent-color: var(--color-brand-cyan);
  height: 18px;
  margin: 0;
  width: 100%;
}

.transport-button,
.volume-button,
.mode-button {
  align-items: center;
  background: rgba(9, 25, 43, 0.58);
  border: 0;
  border-radius: 8px;
  color: var(--color-heading);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-weight: 850;
  justify-content: center;
}

.transport-button {
  height: 44px;
  width: 44px;
}

.transport-button.primary {
  background: rgba(14, 165, 233, 0.34);
}

.volume-button {
  height: 44px;
  width: 44px;
}

.volume-range {
  accent-color: var(--color-brand-cyan);
  width: 96px;
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

@media (max-width: 960px) {
  .media-controls {
    max-width: min(840px, 88vw);
  }

  .volume-range,
  .mode-button span {
    display: none;
  }
}

@media (max-width: 720px) {
  .media-controls {
    gap: 12px;
    max-width: 100%;
  }

  .control-row {
    grid-template-columns: 1fr;
  }

  .track-summary strong,
  .track-summary small {
    max-width: 100%;
  }

  .button-groups {
    flex-wrap: wrap;
    justify-content: end;
  }

  .timeline-row {
    grid-template-columns: minmax(0, 1fr);
  }

  .volume-button,
  .volume-range {
    display: none;
  }
}
</style>
