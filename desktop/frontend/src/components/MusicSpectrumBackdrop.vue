<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({
  audioElement: { type: Object, default: null },
  playing: { type: Boolean, default: false },
});

const emit = defineEmits(["visualizer-error"]);

const canvasRef = ref(null);
const audioContext = ref(null);
const sourceNode = ref(null);
const analyserNode = ref(null);
let canvasContext = null;
let frequencyData = null;
let animationFrameId = 0;
let lastRenderAt = 0;

const TARGET_FRAME_RATE = 12;
const FRAME_INTERVAL_MS = 1000 / TARGET_FRAME_RATE;
const MAX_PIXEL_RATIO = 1.25;
const BAR_COUNT = 12;
const BAR_COLORS = ["#22d3ee", "#38bdf8", "#34d399"];

function requireCanvas() {
  if (!canvasRef.value) {
    throw new Error("音乐频谱需要 canvas");
  }
  return canvasRef.value;
}

function requireCanvasContext() {
  if (canvasContext) return canvasContext;
  const canvas = requireCanvas();
  canvasContext = canvas.getContext("2d");
  if (!canvasContext) {
    throw new Error("当前浏览器不支持 Canvas 2D 音乐频谱");
  }
  return canvasContext;
}

function resizeCanvas() {
  const canvas = requireCanvas();
  const rect = canvas.getBoundingClientRect();
  const pixelRatio = Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO);
  canvas.width = Math.max(1, Math.round(rect.width * pixelRatio));
  canvas.height = Math.max(1, Math.round(rect.height * pixelRatio));
  requireCanvasContext().clearRect(0, 0, canvas.width, canvas.height);
}

function ensureAudioGraph() {
  if (!props.audioElement || analyserNode.value) return;
  audioContext.value = new AudioContext();
  sourceNode.value = audioContext.value.createMediaElementSource(props.audioElement);
  analyserNode.value = audioContext.value.createAnalyser();
  analyserNode.value.fftSize = 64;
  analyserNode.value.smoothingTimeConstant = 0.72;
  sourceNode.value.connect(analyserNode.value);
  analyserNode.value.connect(audioContext.value.destination);
  frequencyData = new Uint8Array(analyserNode.value.frequencyBinCount);
}

function visualizerShouldRender() {
  return props.playing && document.visibilityState === "visible";
}

function stopRendering() {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = 0;
  }
  lastRenderAt = 0;
}

function drawSpectrum() {
  const canvas = requireCanvas();
  const context = requireCanvasContext();
  analyserNode.value.getByteFrequencyData(frequencyData);
  context.clearRect(0, 0, canvas.width, canvas.height);

  const slotWidth = canvas.width / BAR_COUNT;
  const barWidth = Math.max(1, slotWidth * 0.58);
  const centerY = canvas.height / 2;
  for (let index = 0; index < BAR_COUNT; index += 1) {
    const binIndex = Math.floor((index * frequencyData.length) / BAR_COUNT);
    const amplitude = frequencyData[binIndex] / 255;
    const barHeight = Math.max(1, amplitude * canvas.height * 0.88);
    const x = index * slotWidth + (slotWidth - barWidth) / 2;
    context.globalAlpha = 0.42 + amplitude * 0.58;
    context.fillStyle = BAR_COLORS[index % BAR_COLORS.length];
    context.fillRect(x, centerY - barHeight / 2, barWidth, barHeight);
  }
  context.globalAlpha = 1;
}

function formatVisualizerError(err) {
  const message = err instanceof Error ? err.message : String(err);
  return `动态背景初始化失败：${message}`;
}

function reportVisualizerError(err) {
  stopRendering();
  emit("visualizer-error", formatVisualizerError(err));
}

function renderFrame(timestamp) {
  if (!visualizerShouldRender() || !analyserNode.value) {
    animationFrameId = 0;
    return;
  }
  try {
    if (timestamp - lastRenderAt >= FRAME_INTERVAL_MS) {
      drawSpectrum();
      lastRenderAt = timestamp;
    }
    animationFrameId = requestAnimationFrame(renderFrame);
  } catch (err) {
    reportVisualizerError(err);
  }
}

async function startRendering() {
  if (!visualizerShouldRender()) return;
  ensureAudioGraph();
  const context = audioContext.value;
  if (!context || !analyserNode.value) return;
  if (context.state === "suspended") {
    await context.resume();
  }
  if (!visualizerShouldRender()) return;
  if (!animationFrameId) {
    lastRenderAt = performance.now() - FRAME_INTERVAL_MS;
    animationFrameId = requestAnimationFrame(renderFrame);
  }
}

function destroyAudioGraph() {
  stopRendering();
  if (sourceNode.value) {
    sourceNode.value.disconnect();
    sourceNode.value = null;
  }
  if (analyserNode.value) {
    analyserNode.value.disconnect();
    analyserNode.value = null;
  }
  frequencyData = null;
  if (audioContext.value) {
    const context = audioContext.value;
    audioContext.value = null;
    if (context.state !== "closed") {
      void context.close().catch(reportVisualizerError);
    }
  }
}

function syncVisualizerState() {
  if (visualizerShouldRender()) {
    startRendering().catch(reportVisualizerError);
  } else {
    stopRendering();
  }
}

function handleResize() {
  try {
    resizeCanvas();
  } catch (err) {
    reportVisualizerError(err);
  }
}

onMounted(() => {
  window.addEventListener("resize", handleResize);
  document.addEventListener("visibilitychange", syncVisualizerState);
  handleResize();
  syncVisualizerState();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  document.removeEventListener("visibilitychange", syncVisualizerState);
  destroyAudioGraph();
});

watch(
  () => props.playing,
  () => {
    syncVisualizerState();
  },
);

watch(
  () => props.audioElement,
  () => {
    destroyAudioGraph();
    syncVisualizerState();
  },
);
</script>

<template>
  <div :class="['music-spectrum-backdrop', { active: playing }]" aria-hidden="true">
    <canvas ref="canvasRef"></canvas>
  </div>
</template>

<style scoped>
.music-spectrum-backdrop {
  background: radial-gradient(circle at 50% 50%, rgba(14, 165, 233, 0.3), rgba(5, 15, 29, 0.92));
  inset: 0;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  position: absolute;
  transition: opacity 240ms ease;
}

.music-spectrum-backdrop.active {
  opacity: 0.92;
}

.music-spectrum-backdrop canvas {
  display: block;
  height: 100%;
  width: 100%;
}

@media (prefers-reduced-motion: reduce) {
  .music-spectrum-backdrop.active {
    opacity: 0;
  }
}
</style>
