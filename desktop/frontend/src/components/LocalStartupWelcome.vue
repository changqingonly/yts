<script setup>
import { AlertCircle, LoaderCircle, RotateCcw, Sparkles } from "@lucide/vue";
import { computed } from "vue";

const props = defineProps({
  status: { type: String, required: true },
  stage: { type: String, default: "" },
  errorMessage: { type: String, default: "" },
});

defineEmits(["retry", "continue"]);

const startupStages = [
  { key: "sidecar", label: "启动服务" },
  { key: "health", label: "连接曲库" },
  { key: "prepare", label: "准备音乐" },
];

const currentStageIndex = computed(() => {
  const index = startupStages.findIndex((item) => item.key === props.stage);
  return index < 0 ? 0 : index;
});

const stageMessage = computed(() => {
  const messages = {
    sidecar: "正在启动本地音乐服务",
    health: "正在连接你的本地曲库",
    prepare: "正在准备第一首歌曲",
  };
  return messages[props.stage] || "正在准备本地音乐";
});
</script>

<template>
  <section
    :class="['startup-welcome', `is-${status}`]"
    :role="status === 'failed' ? 'alert' : 'status'"
    :aria-busy="status === 'starting'"
    aria-live="polite"
  >
    <div class="startup-atmosphere" aria-hidden="true">
      <span></span>
      <span></span>
    </div>

    <div class="startup-content">
      <div class="startup-mark">
        <span class="startup-brand"><Sparkles :size="27" /></span>
        <LoaderCircle v-if='status === "starting"' :size="54" class="startup-spinner" />
        <AlertCircle v-else :size="28" class="startup-alert" />
      </div>

      <p class="startup-eyebrow">乐兔 · 本地音乐</p>
      <h1 v-if='status === "starting"'>欢迎回来</h1>
      <h1 v-else-if='status === "timeout"'>本地音乐仍在准备中</h1>
      <h1 v-else-if='status === "failed"'>本地服务启动失败</h1>

      <p v-if='status === "starting"' class="startup-lead">{{ stageMessage }}</p>
      <p v-else-if='status === "timeout"' class="startup-lead">
        冷启动时间超过预期，你可以继续等待，或进入音乐页查看详情。
      </p>
      <p v-else class="startup-lead">{{ errorMessage }}</p>

      <ol v-if="status === 'starting'" class="startup-progress" aria-label="启动进度">
        <li
          v-for="(item, index) in startupStages"
          :key="item.key"
          :class="{ active: index === currentStageIndex, completed: index < currentStageIndex }"
        >
          <span></span>
          {{ item.label }}
        </li>
      </ol>

      <small v-if="status === 'starting'">只准备播放所需内容，生成服务将在使用时启动</small>
      <small v-else-if="status === 'timeout'">已等待 30 秒</small>

      <div v-if="status === 'timeout' || status === 'failed'" class="startup-actions">
        <button type="button" class="startup-retry" @click="$emit('retry')">
          <RotateCcw :size="16" />
          <span>{{ status === "timeout" ? "继续等待" : "重试" }}</span>
        </button>
        <button type="button" class="startup-continue" @click="$emit('continue')">
          进入音乐页查看详情
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.startup-welcome {
  align-items: center;
  background:
    radial-gradient(circle at 50% 40%, rgba(10, 120, 145, 0.2), transparent 34%),
    linear-gradient(160deg, #061728 0%, var(--color-bg) 62%);
  color: var(--color-text);
  display: flex;
  inset: 0;
  justify-content: center;
  overflow: hidden;
  padding: 32px;
  position: absolute;
  text-align: center;
  z-index: 80;
}

.startup-atmosphere {
  inset: 0;
  pointer-events: none;
  position: absolute;
}

.startup-atmosphere span {
  border: 1px solid rgba(34, 211, 238, 0.08);
  border-radius: 50%;
  left: 50%;
  position: absolute;
  top: 42%;
  transform: translate(-50%, -50%);
}

.startup-atmosphere span:first-child {
  height: 320px;
  width: 320px;
}

.startup-atmosphere span:last-child {
  height: 470px;
  width: 470px;
}

.startup-content {
  align-items: center;
  display: flex;
  flex-direction: column;
  max-width: 560px;
  position: relative;
  width: 100%;
  z-index: 1;
}

.startup-mark {
  align-items: center;
  display: flex;
  height: 72px;
  justify-content: center;
  position: relative;
  width: 72px;
}

.startup-brand {
  align-items: center;
  color: var(--color-brand-cyan);
  display: inline-flex;
  filter: drop-shadow(0 0 12px var(--color-brand-glow));
  justify-content: center;
}

.startup-alert {
  color: var(--color-brand-cyan);
  filter: drop-shadow(0 0 10px var(--color-brand-glow));
}

.startup-spinner {
  animation: startup-spin 1200ms linear infinite;
  color: rgba(34, 211, 238, 0.45);
  inset: 9px;
  position: absolute;
  stroke-dasharray: 58 30;
}

.startup-eyebrow {
  color: var(--color-brand-cyan);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  margin: 14px 0 0;
  text-transform: uppercase;
}

.startup-welcome h1 {
  color: var(--color-heading);
  font-size: clamp(28px, 4vw, 42px);
  font-weight: 720;
  letter-spacing: -0.04em;
  margin: 9px 0 10px;
}

.startup-lead {
  color: var(--color-muted-strong);
  font-size: 15px;
  line-height: 1.7;
  margin: 0;
  max-width: 520px;
}

.startup-welcome small {
  color: var(--color-muted);
  font-size: 11px;
  margin-top: 18px;
}

.startup-progress {
  display: grid;
  gap: 0;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  list-style: none;
  margin: 34px 0 0;
  padding: 0;
  width: min(390px, 100%);
}

.startup-progress li {
  color: rgba(138, 164, 189, 0.52);
  display: grid;
  font-size: 11px;
  gap: 9px;
  grid-template-rows: 8px auto;
  position: relative;
}

.startup-progress li::before {
  background: rgba(138, 164, 189, 0.16);
  content: "";
  height: 1px;
  left: 0;
  position: absolute;
  right: 0;
  top: 4px;
}

.startup-progress li:first-child::before {
  left: 50%;
}

.startup-progress li:last-child::before {
  right: 50%;
}

.startup-progress li > span {
  background: #16344a;
  border: 2px solid #4e6c82;
  border-radius: 50%;
  height: 8px;
  justify-self: center;
  position: relative;
  width: 8px;
  z-index: 1;
}

.startup-progress li.active,
.startup-progress li.completed {
  color: var(--color-muted-strong);
}

.startup-progress li.active > span {
  animation: startup-pulse 1500ms ease-in-out infinite;
  background: var(--color-brand-cyan);
  border-color: var(--color-brand-cyan);
  box-shadow: 0 0 0 5px rgba(34, 211, 238, 0.12);
}

.startup-progress li.completed > span {
  background: var(--color-brand-green);
  border-color: var(--color-brand-green);
}

.startup-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.startup-actions button {
  align-items: center;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  color: var(--color-text);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-size: 13px;
  font-weight: 750;
  gap: 7px;
  min-height: 38px;
  padding: 0 14px;
}

.startup-actions button:hover {
  border-color: rgba(34, 211, 238, 0.46);
}

.startup-retry {
  background: rgba(14, 165, 233, 0.24) !important;
  border-color: rgba(34, 211, 238, 0.3) !important;
}

.startup-continue {
  color: var(--color-muted-strong) !important;
}

@keyframes startup-spin {
  to { transform: rotate(360deg); }
}

@keyframes startup-pulse {
  50% { box-shadow: 0 0 0 9px rgba(34, 211, 238, 0.04); }
}

@media (prefers-reduced-motion: reduce) {
  .startup-spinner,
  .startup-progress li.active > span {
    animation: none;
  }
}
</style>
