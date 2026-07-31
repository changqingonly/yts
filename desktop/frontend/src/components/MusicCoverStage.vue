<script setup>
import { CircleAlert, RefreshCw, Trash2 } from "@lucide/vue";
import { computed } from "vue";

const props = defineProps({
  coverUrl: { type: String, default: "" },
  playing: { type: Boolean, default: false },
  status: { type: String, default: "absent" },
});

const emit = defineEmits(["delete", "regenerate", "retry"]);
const generating = computed(() => props.status === "queued" || props.status === "generating");
const failed = computed(() => props.status === "failed");
const suppressed = computed(() => props.status === "suppressed");
</script>

<template>
  <section class="cover-stage" aria-label="歌曲封面">
    <div :class="['cover-vinyl', { spinning: playing }]">
      <span class="vinyl-grooves" aria-hidden="true"></span>
      <img v-if="coverUrl" class="vinyl-label cover-image" :src="coverUrl" alt="当前歌曲封面" />
      <span v-else class="vinyl-label default-label" aria-hidden="true">
        <span class="label-mark"></span>
      </span>
      <span class="spindle" aria-hidden="true"></span>
    </div>

    <div class="cover-tools" aria-label="封面操作">
      <button type="button" title="重新生成封面" aria-label="重新生成封面" @click="emit('regenerate')">
        <RefreshCw :size="16" />
      </button>
      <button
        v-if="coverUrl"
        type="button"
        title="删除生成封面"
        aria-label="删除生成封面"
        @click="emit('delete')"
      >
        <Trash2 :size="16" />
      </button>
    </div>

    <div class="cover-status" aria-live="polite">
      <span v-if="generating" class="status-copy">
        <span class="status-pulse"></span>
        正在后台生成封面
      </span>
      <template v-else-if="failed">
        <span class="status-copy"><CircleAlert :size="14" />封面生成失败</span>
        <button class="text-action" type="button" @click="emit('retry')">重试</button>
      </template>
      <template v-else-if="suppressed">
        <span class="status-copy">未设置封面</span>
        <button class="text-action" type="button" @click="emit('regenerate')">生成封面</button>
      </template>
      <template v-else-if="status === 'unavailable'">
        <span class="status-copy"><CircleAlert :size="14" />本地图片模型未安装</span>
      </template>
    </div>

  </section>
</template>

<style scoped>
.cover-stage {
  align-self: center;
  display: grid;
  grid-template-rows: auto 28px;
  justify-items: center;
  min-height: 310px;
  position: relative;
  z-index: 1;
}

.cover-vinyl {
  aspect-ratio: 1;
  background: #0b1118;
  border: 1px solid rgba(169, 202, 220, 0.2);
  border-radius: 50%;
  box-shadow: 0 24px 64px rgba(0, 5, 12, 0.48), 0 0 44px rgba(34, 211, 238, 0.1);
  max-width: 260px;
  overflow: hidden;
  position: relative;
  width: min(31vh, 260px);
}

.cover-vinyl.spinning {
  animation: cover-disc-spin 14s linear infinite;
}

.vinyl-grooves {
  background: repeating-radial-gradient(
    circle,
    transparent 0 5px,
    rgba(166, 199, 216, 0.12) 6px,
    transparent 7px 10px
  );
  inset: 4%;
  position: absolute;
}

.vinyl-label {
  border: 1px solid rgba(224, 243, 250, 0.28);
  border-radius: 50%;
  inset: 27%;
  position: absolute;
}

.cover-image {
  height: 46%;
  object-fit: cover;
  width: 46%;
}

.default-label {
  align-items: center;
  background: #126070;
  display: flex;
  justify-content: center;
}

.label-mark {
  border: 2px solid rgba(229, 250, 252, 0.88);
  border-radius: 50%;
  height: 28%;
  width: 28%;
}

.spindle {
  background: #e5f6f8;
  border-radius: 50%;
  height: 6px;
  left: 50%;
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 6px;
}

.cover-tools {
  display: flex;
  gap: 6px;
  opacity: 0;
  position: absolute;
  right: calc(50% - min(15.5vh, 130px));
  top: 8px;
  transition: opacity 140ms ease;
}

.cover-stage:hover .cover-tools,
.cover-stage:focus-within .cover-tools {
  opacity: 1;
}

.cover-tools button {
  align-items: center;
  background: rgba(5, 15, 25, 0.84);
  border: 1px solid rgba(158, 201, 220, 0.24);
  border-radius: 6px;
  color: #d8e8ef;
  cursor: pointer;
  display: inline-flex;
  height: 30px;
  justify-content: center;
  width: 30px;
}

.cover-status {
  align-items: center;
  color: #8da5b4;
  display: flex;
  font-size: 12px;
  gap: 8px;
  height: 28px;
  justify-content: center;
  margin-top: 10px;
}

.status-copy {
  align-items: center;
  display: inline-flex;
  gap: 6px;
}

.status-pulse {
  animation: status-breathe 1.8s ease-in-out infinite;
  background: #2bc6ca;
  border-radius: 50%;
  height: 6px;
  width: 6px;
}

.text-action {
  background: transparent;
  border: 0;
  color: #8be0e2;
  cursor: pointer;
  font: inherit;
  padding: 2px 0;
}

@keyframes cover-disc-spin {
  to { transform: rotate(360deg); }
}

@keyframes status-breathe {
  50% { opacity: 0.32; }
}

@media (prefers-reduced-motion: reduce) {
  .cover-vinyl.spinning,
  .status-pulse {
    animation: none;
  }
}

@media (max-width: 720px) {
  .cover-stage {
    min-height: 220px;
  }

  .cover-vinyl {
    width: min(24vh, 176px);
  }

  .cover-tools {
    right: calc(50% - min(12vh, 88px));
  }
}
</style>
