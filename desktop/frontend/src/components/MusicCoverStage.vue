<script setup>
import { CircleAlert, Disc3, RefreshCw, Trash2 } from "@lucide/vue";
import { computed } from "vue";

const props = defineProps({
  coverUrl: { type: String, default: "" },
  themeColor: { type: String, default: "" },
  track: { type: Object, default: null },
  playing: { type: Boolean, default: false },
  status: { type: String, default: "absent" },
});

const emit = defineEmits(["delete", "regenerate", "retry"]);
const generating = computed(() => props.status === "queued" || props.status === "generating");
const failed = computed(() => props.status === "failed");
const suppressed = computed(() => props.status === "suppressed");
const trackTitle = computed(() => props.track?.title || "未命名歌曲");
const trackArtist = computed(() => props.track?.artist || "未知艺人");
const artworkThemeStyle = computed(() =>
  props.themeColor ? { "--artwork-accent": props.themeColor } : {},
);
</script>

<template>
  <section class="cover-stage" aria-label="歌曲封面与歌词">
    <div class="artwork-column">
      <div class="cover-artwork" :style="artworkThemeStyle">
        <img v-if="coverUrl" :src="coverUrl" alt="当前歌曲封面" />
        <div v-else class="cover-placeholder" aria-hidden="true">
          <Disc3 :size="54" :class="{ spinning: playing }" />
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
      </div>

      <div class="cover-caption">
        <div>
          <h2>{{ trackTitle }}</h2>
          <p>{{ trackArtist }}</p>
        </div>
        <div class="cover-status" aria-live="polite">
          <span v-if="generating" class="status-copy">
            <span class="status-pulse"></span>正在后台生成封面
          </span>
          <template v-else-if="failed">
            <span class="status-copy"><CircleAlert :size="14" />封面生成失败</span>
            <button class="text-action" type="button" @click="emit('retry')">重试</button>
          </template>
          <template v-else-if="suppressed">
            <span class="status-copy">未设置封面</span>
            <button class="text-action" type="button" @click="emit('regenerate')">生成封面</button>
          </template>
          <span v-else-if="status === 'unavailable'" class="status-copy">
            <CircleAlert :size="14" />本地图片模型未安装
          </span>
        </div>
      </div>
    </div>

    <aside class="track-context" aria-label="歌词">
      <section class="lyrics-region" aria-label="歌词">
        <span>歌词</span>
        <div class="lyrics-empty">
          <p>暂无歌词</p>
        </div>
      </section>
    </aside>
  </section>
</template>

<style scoped>
.cover-stage {
  align-items: center;
  display: grid;
  gap: clamp(40px, 6vw, 96px);
  grid-template-columns: minmax(300px, 0.9fr) minmax(320px, 1.1fr);
  height: 100%;
  min-height: 0;
  position: relative;
  width: min(1120px, 100%);
  z-index: 1;
}

.artwork-column {
  align-self: center;
  display: grid;
  gap: 18px;
  justify-items: center;
  min-width: 0;
}

.cover-artwork {
  --artwork-accent: #14758a;

  aspect-ratio: 1 / 1;
  background: color-mix(in srgb, var(--artwork-accent) 18%, #07111d);
  box-shadow: 0 30px 78px rgba(0, 4, 12, 0.5), 0 0 52px color-mix(in srgb, var(--artwork-accent) 24%, transparent);
  max-width: 430px;
  overflow: hidden;
  position: relative;
  width: min(42vh, 100%);
}

.cover-artwork img {
  display: block;
  height: 100%;
  object-fit: cover;
  width: 100%;
}

.cover-placeholder {
  align-items: center;
  color: rgba(220, 239, 246, 0.68);
  display: flex;
  height: 100%;
  justify-content: center;
}

.cover-placeholder .spinning {
  animation: cover-disc-spin 14s linear infinite;
}

.cover-tools {
  display: flex;
  gap: 6px;
  opacity: 0;
  position: absolute;
  right: 12px;
  top: 12px;
  transition: opacity 140ms ease;
}

.cover-artwork:hover .cover-tools,
.cover-artwork:focus-within .cover-tools {
  opacity: 1;
}

.cover-tools button {
  align-items: center;
  background: rgba(5, 15, 25, 0.84);
  border: 1px solid rgba(224, 243, 250, 0.24);
  border-radius: 6px;
  color: #d8e8ef;
  cursor: pointer;
  display: inline-flex;
  height: 32px;
  justify-content: center;
  width: 32px;
}

.cover-caption {
  align-items: start;
  display: flex;
  justify-content: space-between;
  max-width: 430px;
  width: min(42vh, 100%);
}

.cover-caption h2 {
  color: var(--color-heading);
  font-size: 24px;
  letter-spacing: 0;
  margin: 0;
}

.cover-caption p {
  color: var(--color-muted-strong);
  font-size: 14px;
  margin: 6px 0 0;
}

.cover-status {
  align-items: center;
  color: #8da5b4;
  display: flex;
  font-size: 12px;
  gap: 8px;
  min-height: 28px;
  justify-content: end;
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

.track-context {
  align-self: stretch;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  min-height: 320px;
  padding: 14px 0;
}

.lyrics-region > span {
  color: rgba(216, 231, 245, 0.58);
  display: block;
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 10px;
}

.lyrics-region {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
}

.lyrics-empty {
  align-items: center;
  border-left: 2px solid color-mix(in srgb, var(--artwork-accent) 56%, transparent);
  display: flex;
  min-height: 180px;
  padding-left: 24px;
}

.lyrics-empty p {
  color: rgba(216, 231, 245, 0.48);
  font-size: 22px;
  font-weight: 750;
  margin: 0;
}

@keyframes cover-disc-spin { to { transform: rotate(360deg); } }
@keyframes status-breathe { 50% { opacity: 0.32; } }

@media (prefers-reduced-motion: reduce) {
  .cover-placeholder .spinning,
  .status-pulse { animation: none; }
}

@media (max-width: 820px) {
  .cover-stage {
    gap: 28px;
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .cover-artwork,
  .cover-caption {
    width: min(360px, 100%);
  }

  .track-context {
    min-height: 240px;
  }
}
</style>
