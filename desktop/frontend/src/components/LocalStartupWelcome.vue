<script setup>
import { AlertCircle, LoaderCircle, RotateCcw } from "@lucide/vue";

defineProps({
  status: { type: String, required: true },
  stage: { type: String, default: "" },
  errorMessage: { type: String, default: "" },
});

defineEmits(["retry", "continue"]);
</script>

<template>
  <section class="startup-welcome" role="status" aria-live="polite">
    <div class="startup-mark">
      <LoaderCircle v-if='status === "starting"' :size="30" class="startup-spinner" />
      <AlertCircle v-else :size="30" />
    </div>
    <h1 v-if='status === "starting"'>正在准备音乐</h1>
    <h1 v-else-if='status === "timeout"'>本地服务启动较慢</h1>
    <h1 v-else-if='status === "failed"'>启动失败</h1>
    <p v-if='status === "starting"'>连接本地曲库并准备第一首歌曲...</p>
    <p v-else>{{ errorMessage }}</p>
    <small v-if="stage">阶段：{{ stage }}</small>
    <div v-if="status === 'timeout' || status === 'failed'" class="startup-actions">
      <button type="button" title="重试" @click="$emit('retry')">
        <RotateCcw :size="17" />
        <span>重试</span>
      </button>
      <button type="button" class="startup-continue" @click="$emit('continue')">
        进入音乐页查看详情
      </button>
    </div>
  </section>
</template>

<style scoped>
.startup-welcome {
  align-items: center;
  background: var(--color-bg);
  color: var(--color-text);
  display: flex;
  flex-direction: column;
  inset: 0;
  justify-content: center;
  padding: 32px;
  position: absolute;
  text-align: center;
  z-index: 80;
}

.startup-mark {
  align-items: center;
  color: var(--color-brand-cyan);
  display: flex;
  height: 40px;
  justify-content: center;
  width: 40px;
}

.startup-spinner {
  animation: startup-spin 900ms linear infinite;
}

.startup-welcome h1 {
  font-size: 22px;
  letter-spacing: 0;
  margin: 16px 0 6px;
}

.startup-welcome p {
  color: var(--color-text-muted);
  margin: 0;
  max-width: 520px;
}

.startup-welcome small {
  color: var(--color-text-muted);
  margin-top: 10px;
}

.startup-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.startup-actions button {
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  display: inline-flex;
  gap: 7px;
  min-height: 38px;
  padding: 0 14px;
}

.startup-continue {
  background: transparent;
  color: var(--color-text);
}

@keyframes startup-spin {
  to { transform: rotate(360deg); }
}
</style>
