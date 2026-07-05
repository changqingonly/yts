<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Repeat1, Repeat2, Shuffle, SkipBack, SkipForward } from "@lucide/vue";
import "media-chrome";
import WaveSurfer from "wavesurfer.js";

const props = defineProps({
  track: { type: Object, default: null },
  playing: { type: Boolean, default: false },
  loopMode: { type: String, required: true },
  loopLabel: { type: String, required: true },
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
]);

const audioRef = ref(null);
const waveformRef = ref(null);
const wave = ref(null);
const waveReady = ref(false);
const currentTime = ref(0);
const duration = ref(0);

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

function requireWaveform() {
  if (!waveformRef.value) {
    throw new Error("YtsAudioPlayer requires a waveform container");
  }
  return waveformRef.value;
}

function createWave() {
  wave.value = WaveSurfer.create({
    autoCenter: true,
    barGap: 5,
    barMinHeight: 4,
    barRadius: 8,
    barWidth: 6,
    container: requireWaveform(),
    cursorColor: "transparent",
    cursorWidth: 0,
    dragToSeek: true,
    height: "auto",
    hideScrollbar: true,
    interact: true,
    media: requireAudio(),
    normalize: true,
    progressColor: "rgba(34, 211, 238, 0.94)",
    waveColor: "rgba(52, 211, 153, 0.24)",
  });
  wave.value.on("ready", (duration) => {
    waveReady.value = true;
    setDuration(duration);
  });
  wave.value.on("timeupdate", (currentTime) => setCurrentTime(currentTime));
  wave.value.on("error", (err) => {
    emit("play-error", formatPlaybackError(err));
  });
  if (sourceUrl.value) {
    const loading = wave.value.load(sourceUrl.value);
    loading?.catch?.((err) => emit("play-error", formatPlaybackError(err)));
  } else {
    wave.value.empty();
  }
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

async function syncPlaybackIntent() {
  const audio = requireAudio();
  if (!sourceUrl.value) {
    audio.pause();
    return;
  }
  if (props.playing && audio.paused) {
    try {
      await audio.play();
    } catch (err) {
      emit("play-error", formatPlaybackError(err));
    }
  } else if (!props.playing && !audio.paused) {
    audio.pause();
  }
}

function formatPlaybackError(err) {
  const mediaError = err?.currentTarget?.error || err?.target?.error || err;
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

function handlePlay() {
  emit("play");
}

function handlePause() {
  emit("pause");
}

function handleEnded() {
  emit("ended");
}

function handleTimeUpdate(event) {
  setCurrentTime(event.currentTarget.currentTime);
}

function handleDurationChange(event) {
  setDuration(event.currentTarget.duration || 0);
}

function handleAudioError(event) {
  emit("play-error", formatPlaybackError(event));
}

onMounted(() => {
  createWave();
});

onBeforeUnmount(() => {
  if (wave.value) {
    wave.value.destroy();
    wave.value = null;
  }
});

watch(sourceUrl, async (url) => {
  if (!wave.value) return;
  waveReady.value = false;
  currentTime.value = 0;
  duration.value = 0;
  try {
    if (url) {
      await wave.value.load(url);
    } else {
      wave.value.empty();
    }
    await nextTick();
    await syncPlaybackIntent();
  } catch (err) {
    emit("play-error", formatPlaybackError(err));
  }
});

watch(
  () => props.playing,
  async () => {
    await syncPlaybackIntent();
  },
);
</script>

<template>
  <section class="yts-audio-player" :class="{ empty: !sourceUrl, playing }">
    <div class="hero-wave" aria-label="音频波形">
      <div ref="waveformRef" class="waveform-canvas"></div>
      <p v-if="!sourceUrl" class="wave-empty">暂无歌曲</p>
      <p v-else-if="!waveReady" class="wave-empty">载入中</p>
    </div>

    <media-controller class="media-shell" audio>
      <audio
        ref="audioRef"
        slot="media"
        :loop="loopMode === 'single'"
        :src="sourceUrl || undefined"
        preload="metadata"
        @durationchange="handleDurationChange"
        @ended="handleEnded"
        @error="handleAudioError"
        @pause="handlePause"
        @play="handlePlay"
        @timeupdate="handleTimeUpdate"
      ></audio>

      <media-control-bar class="media-controls">
        <div class="time-progress" aria-label="时间进度">
          时间进度：{{ currentTimeLabel }}/{{ durationLabel }}
        </div>
        <div class="timeline-row" aria-label="播放进度">
          <media-time-range></media-time-range>
        </div>
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
              <media-play-button></media-play-button>
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
              <media-mute-button></media-mute-button>
              <media-volume-range></media-volume-range>
              <button class="mode-button" type="button" title="播放模式" @click="emit('cycle-loop')">
                <component :is="loopIcon" :size="18" />
                <span>{{ loopLabel }}</span>
              </button>
            </div>
          </div>
        </div>
      </media-control-bar>
    </media-controller>
  </section>
</template>

<style scoped>
.yts-audio-player {
  display: grid;
  gap: clamp(18px, 3.2vh, 34px);
  grid-template-rows: minmax(220px, 1fr) auto;
  height: 100%;
  min-height: 0;
  position: relative;
  z-index: 1;
}

.hero-wave {
  -webkit-mask-image: radial-gradient(ellipse at center, #000 42%, rgba(0, 0, 0, 0.72) 66%, transparent 100%);
  align-self: center;
  background: transparent;
  border: 0;
  border-radius: 0;
  height: clamp(330px, 52vh, 500px);
  justify-self: center;
  mask-image: radial-gradient(ellipse at center, #000 42%, rgba(0, 0, 0, 0.72) 66%, transparent 100%);
  max-width: 1180px;
  overflow: hidden;
  position: relative;
  width: min(78vw, 1180px);
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

.hero-wave::after {
  background:
    linear-gradient(90deg, transparent 0%, rgba(34, 211, 238, 0.18) 38%, rgba(52, 211, 153, 0.2) 50%, transparent 68%),
    repeating-linear-gradient(90deg, transparent 0 18px, rgba(125, 211, 252, 0.08) 18px 23px);
  content: "";
  inset: 0;
  opacity: 0;
  pointer-events: none;
  position: absolute;
  transform: translateX(-12%) scaleY(0.98);
  z-index: 2;
}

.yts-audio-player.playing .hero-wave::after {
  animation:
    waveform-shimmer 1.8s linear infinite,
    waveform-breathe 2.4s ease-in-out infinite;
  opacity: 1;
}

.yts-audio-player.playing .waveform-canvas {
  animation: waveform-breathe 2.4s ease-in-out infinite;
  transform-origin: center;
}

.waveform-canvas {
  height: 100%;
  position: relative;
  z-index: 1;
}

.wave-empty {
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 850;
  inset: 50% auto auto 50%;
  margin: 0;
  position: absolute;
  transform: translate(-50%, -50%);
  z-index: 2;
}

.media-shell {
  --media-accent-color: var(--color-brand-cyan);
  --media-background-color: transparent;
  --media-control-background: rgba(9, 25, 43, 0.52);
  --media-control-hover-background: rgba(14, 165, 233, 0.22);
  --media-primary-color: var(--color-heading);
  --media-secondary-color: rgba(138, 164, 189, 0.72);
  --media-text-color: var(--color-heading);
  --media-time-range-buffered-color: rgba(138, 164, 189, 0.18);
  --media-time-range-track-background: rgba(138, 164, 189, 0.14);

  background: transparent;
  border: 0;
  box-shadow: none;
  color: var(--color-heading);
  display: block;
  justify-self: stretch;
  min-width: 0;
  width: 100%;
}

.media-controls {
  background: transparent;
  display: grid;
  gap: 12px;
  grid-template-rows: auto auto auto;
  margin-inline: auto;
  max-width: none;
  min-width: 0;
  width: 100%;
}

.time-progress {
  color: rgba(216, 231, 245, 0.82);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  font-weight: 850;
  justify-self: center;
  line-height: 1.2;
  min-height: 16px;
  text-align: center;
}

.timeline-row {
  align-items: center;
  display: grid;
  gap: 0;
  grid-template-columns: minmax(0, 1fr);
  margin-inline: calc(0px - var(--stage-x-pad, 0px));
  min-width: 0;
  width: calc(100% + var(--stage-x-pad, 0px) + var(--stage-x-pad, 0px));
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

media-play-button,
media-mute-button,
media-time-display,
media-duration-display,
media-time-range,
media-volume-range {
  border-radius: 8px;
}

media-time-range {
  width: 100%;
}

.transport-button,
.mode-button {
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

.transport-button {
  height: 44px;
  width: 44px;
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

@keyframes waveform-shimmer {
  from {
    background-position: -32% 0, 0 0;
  }

  to {
    background-position: 132% 0, 34px 0;
  }
}

@keyframes waveform-breathe {
  0%,
  100% {
    transform: scaleY(0.98);
  }

  50% {
    transform: scaleY(1.025);
  }
}

@media (prefers-reduced-motion: reduce) {
  .yts-audio-player.playing .hero-wave::after,
  .yts-audio-player.playing .waveform-canvas {
    animation: none;
  }
}

@media (max-width: 960px) {
  .hero-wave {
    height: 330px;
    width: min(82vw, 760px);
  }

  .media-controls {
    max-width: min(840px, 88vw);
  }

  media-volume-range,
  .mode-button span {
    display: none;
  }
}

@media (max-width: 720px) {
  .hero-wave {
    height: 280px;
    width: 100%;
  }

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

  media-time-display,
  media-duration-display,
  media-mute-button,
  media-volume-range {
    display: none;
  }
}
</style>
