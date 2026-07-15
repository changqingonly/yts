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
const visualizer = ref(null);
const butterchurn = ref(null);
const butterchurnPresets = ref(null);
let animationFrameId = 0;

const PRESET_NAME = "Flexi, martin + geiss - dedicated to the sherwin maxawow";
const WEBGL_OPTIONS = {
  alpha: false,
  antialias: false,
  depth: false,
  premultipliedAlpha: false,
  stencil: false,
};

async function loadButterchurnLibraries() {
  if (butterchurn.value && butterchurnPresets.value) return;
  const [butterchurnModule, presetsModule] = await Promise.all([
    import("butterchurn"),
    import("butterchurn-presets"),
  ]);
  butterchurn.value = butterchurnModule.default;
  butterchurnPresets.value = presetsModule.default;
}

function requireCanvas() {
  if (!canvasRef.value) {
    throw new Error("Butterchurn 动态背景需要 canvas");
  }
  return canvasRef.value;
}

function assertWebgl2Support() {
  if (!canvasRef.value.getContext("webgl2", WEBGL_OPTIONS)) {
    throw new Error("当前浏览器不支持 WebGL2 动态背景");
  }
}

function requirePreset() {
  const presets = butterchurnPresets.value.getPresets();
  const selectedPreset = presets[PRESET_NAME];
  if (!selectedPreset) {
    throw new Error(`Butterchurn 预设不存在：${PRESET_NAME}`);
  }
  return selectedPreset;
}

function resizeVisualizer() {
  const canvas = requireCanvas();
  const rect = canvas.getBoundingClientRect();
  const pixelRatio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * pixelRatio));
  const height = Math.max(1, Math.round(rect.height * pixelRatio));
  canvas.width = width;
  canvas.height = height;
  if (visualizer.value) {
    visualizer.value.setRendererSize(width, height);
  }
}

async function ensureVisualizer() {
  if (!props.audioElement) return;
  if (visualizer.value) return;
  await loadButterchurnLibraries();
  resizeVisualizer();
  assertWebgl2Support();
  audioContext.value = new AudioContext();
  sourceNode.value = audioContext.value.createMediaElementSource(props.audioElement);
  sourceNode.value.connect(audioContext.value.destination);
  visualizer.value = butterchurn.value.createVisualizer(audioContext.value, canvasRef.value, {
    height: canvasRef.value.height,
    width: canvasRef.value.width,
  });
  visualizer.value.connectAudio(sourceNode.value);
  const selectedPreset = requirePreset();
  visualizer.value.loadPreset(selectedPreset, 0);
}

function stopRendering() {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = 0;
  }
}

function renderFrame() {
  if (!props.playing || !visualizer.value) {
    animationFrameId = 0;
    return;
  }
  visualizer.value.render();
  animationFrameId = requestAnimationFrame(renderFrame);
}

async function startRendering() {
  await ensureVisualizer();
  if (!visualizer.value || !audioContext.value) return;
  if (audioContext.value.state === "suspended") {
    await audioContext.value.resume();
  }
  if (!animationFrameId) {
    renderFrame();
  }
}

function formatVisualizerError(err) {
  const message = err instanceof Error ? err.message : String(err);
  return `动态背景初始化失败：${message}`;
}

function reportVisualizerError(err) {
  stopRendering();
  emit("visualizer-error", formatVisualizerError(err));
}

function destroyVisualizer() {
  stopRendering();
  if (visualizer.value && sourceNode.value) {
    visualizer.value.disconnectAudio(sourceNode.value);
  }
  if (sourceNode.value) {
    sourceNode.value.disconnect();
    sourceNode.value = null;
  }
  if (audioContext.value) {
    const context = audioContext.value;
    audioContext.value = null;
    if (context.state !== "closed") {
      void context.close().catch(reportVisualizerError);
    }
  }
  visualizer.value = null;
}

function syncVisualizerState() {
  if (props.playing) {
    startRendering().catch(reportVisualizerError);
  } else {
    stopRendering();
  }
}

onMounted(() => {
  window.addEventListener("resize", resizeVisualizer);
  syncVisualizerState();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeVisualizer);
  destroyVisualizer();
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
    destroyVisualizer();
    syncVisualizerState();
  },
);
</script>

<template>
  <div :class="['music-butterchurn-backdrop', { active: playing }]" aria-hidden="true">
    <canvas ref="canvasRef"></canvas>
  </div>
</template>

<style scoped>
.music-butterchurn-backdrop {
  inset: 0;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  position: absolute;
  transition: opacity 420ms ease;
}

.music-butterchurn-backdrop.active {
  opacity: 0.9;
}

.music-butterchurn-backdrop::after {
  background:
    radial-gradient(circle at 50% 42%, transparent 0 64%, rgba(4, 11, 21, 0.24) 100%),
    linear-gradient(180deg, rgba(4, 11, 21, 0.02), rgba(4, 11, 21, 0.18));
  content: "";
  inset: 0;
  pointer-events: none;
  position: absolute;
}

.music-butterchurn-backdrop canvas {
  display: block;
  filter: saturate(1.5) contrast(1.08);
  height: 100%;
  transform: scale(1.04);
  width: 100%;
}

@media (prefers-reduced-motion: reduce) {
  .music-butterchurn-backdrop.active {
    opacity: 0;
  }
}
</style>
