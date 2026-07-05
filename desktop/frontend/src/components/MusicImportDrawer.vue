<script setup>
import { computed, ref } from "vue";
import { AlertTriangle, CheckCircle2, FileAudio, RotateCcw, Upload, X } from "@lucide/vue";
import { uploadSong } from "../services/music";
import { usePlaylistStore } from "../stores/playlist";

const props = defineProps({
  open: { type: Boolean, default: false },
  target: { type: String, required: true },
});

const emit = defineEmits(["close", "imported"]);

const playlist = usePlaylistStore();
const fileInput = ref(null);
const tasks = ref([]);
const deviceId = computed(() => readDeviceId());

const targetLabel = computed(() => (props.target === "local" ? "本地" : "云端"));
const currentTargetLabel = computed(
  () => `${targetLabel.value}歌单 · ${playlist.currentPlaylist?.name || "默认歌单"}`,
);
const remainingCapacity = computed(() =>
  Math.max(0, 2000 - (playlist.currentPlaylist?.item_count || playlist.activeItems.length || 0)),
);
const hasTasks = computed(() => tasks.value.length > 0);

const statusLabels = {
  queued: "排队中",
  uploading: "上传中",
  uploaded: "已上传",
  syncing: "写入歌单",
  done: "已完成",
  failed: "失败",
};

function openPicker() {
  if (!fileInput.value) {
    throw new Error("MusicImportDrawer requires file input");
  }
  fileInput.value.click();
}

function handleFileSelect(event) {
  const selectedFiles = Array.from(event.target.files || []);
  const allowedCount = remainingCapacity.value;
  selectedFiles.forEach((file, index) => {
    const task = fileTask(file);
    tasks.value.unshift(task);
    if (index >= allowedCount) {
      task.status = "failed";
      task.error = "超过歌单容量，最多 2000 首";
      return;
    }
    startImport(task);
  });
  event.target.value = "";
}

function fileTask(file) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    file,
    filename: file.name,
    titleAlias: stripExtension(file.name),
    status: "queued",
    error: "",
    uploadResult: null,
  };
}

async function startImport(task) {
  task.error = "";
  try {
    if (!task.uploadResult) {
      task.status = "uploading";
      task.uploadResult = await uploadSong({
        file: task.file,
        mime: task.file.type,
        filename: task.file.name,
      });
      task.status = "uploaded";
    }
    task.status = "syncing";
    await playlist.appendItems([
      {
        content_hash: task.uploadResult.content_hash,
        title_alias: task.titleAlias,
        artist_alias: "",
        device_id: deviceId.value,
      },
    ]);
    task.status = "done";
    emit("imported");
  } catch (err) {
    task.status = "failed";
    task.error = err instanceof Error ? err.message : String(err);
  }
}

function retryImport(task) {
  if (task.status !== "failed") return;
  startImport(task);
}

function stripExtension(filename) {
  const dotIndex = filename.lastIndexOf(".");
  if (dotIndex <= 0) return filename;
  return filename.slice(0, dotIndex);
}

function readDeviceId() {
  const key = "yts-music-device-id";
  const stored = localStorage.getItem(key);
  if (stored) return stored;
  const next = `web-${crypto.randomUUID()}`;
  localStorage.setItem(key, next);
  return next;
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="import-layer" role="presentation">
      <button class="import-scrim" type="button" aria-label="关闭导入面板" @click="emit('close')"></button>
      <aside class="import-drawer" aria-label="导入本地歌曲">
        <header class="drawer-titlebar">
          <div class="drawer-title">
            <span><Upload :size="18" /></span>
            <div>
              <p>导入本地歌曲</p>
              <h2>将导入到 {{ currentTargetLabel }}</h2>
            </div>
          </div>
          <button class="icon-button" type="button" title="关闭" @click="emit('close')">
            <X :size="18" />
          </button>
        </header>

        <section class="capacity-strip">
          <strong>最多 2000 首</strong>
          <span>剩余 {{ remainingCapacity }} 首可添加</span>
        </section>

        <div class="picker-zone">
          <input
            ref="fileInput"
            accept="audio/*"
            class="file-input"
            multiple
            type="file"
            @change="handleFileSelect"
          />
          <button class="pick-button" type="button" @click="openPicker">
            <FileAudio :size="18" />
            <span>选择音频文件</span>
          </button>
        </div>

        <section class="task-stack" aria-label="导入任务">
          <article v-for="task in tasks" :key="task.id" :class="['task-row', task.status]">
            <div class="task-icon">
              <AlertTriangle v-if="task.status === 'failed'" :size="18" />
              <CheckCircle2 v-else-if="task.status === 'done'" :size="18" />
              <FileAudio v-else :size="18" />
            </div>
            <div class="task-copy">
              <strong>{{ task.titleAlias }}</strong>
              <small>{{ statusLabels[task.status] }}</small>
              <p v-if="task.error">{{ task.error }}</p>
            </div>
            <button
              v-if="task.status === 'failed'"
              class="retry-button"
              type="button"
              title="重试"
              @click="retryImport(task)"
            >
              <RotateCcw :size="16" />
            </button>
          </article>
          <p v-if="!hasTasks" class="drawer-empty">选择一个或多个音频文件，导入后会写入当前环境的歌单。</p>
        </section>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.import-layer {
  inset: 0;
  pointer-events: none;
  position: fixed;
  z-index: 40;
}

.import-scrim {
  background: rgba(2, 8, 18, 0.28);
  border: 0;
  cursor: pointer;
  inset: 0;
  pointer-events: auto;
  position: absolute;
}

.import-drawer {
  background:
    radial-gradient(circle at 18% 0%, rgba(34, 211, 238, 0.12), transparent 38%),
    linear-gradient(180deg, rgba(17, 47, 73, 0.98), rgba(5, 17, 31, 0.98));
  box-shadow: -26px 0 72px rgba(0, 7, 18, 0.42);
  color: var(--color-text);
  display: grid;
  gap: 18px;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  height: 100%;
  max-width: min(430px, calc(100vw - 74px));
  overflow: hidden;
  padding: 22px;
  pointer-events: auto;
  position: absolute;
  right: 0;
  top: 0;
  width: 430px;
}

.drawer-titlebar {
  align-items: start;
  display: flex;
  gap: 14px;
  justify-content: space-between;
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

.drawer-title p,
.drawer-title h2,
.drawer-empty,
.task-copy p {
  margin: 0;
}

.drawer-title p {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 850;
}

.drawer-title h2 {
  color: var(--color-heading);
  font-size: 20px;
  line-height: 1.18;
}

.icon-button,
.retry-button,
.pick-button {
  align-items: center;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  justify-content: center;
}

.icon-button,
.retry-button {
  background: rgba(9, 25, 43, 0.72);
  color: var(--color-heading);
  height: 36px;
  width: 36px;
}

.capacity-strip {
  align-items: center;
  background: rgba(4, 16, 31, 0.5);
  border-radius: 8px;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 12px 14px;
}

.capacity-strip strong {
  color: var(--color-heading);
  font-size: 14px;
}

.capacity-strip span {
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 750;
}

.picker-zone {
  display: grid;
}

.file-input {
  display: none;
}

.pick-button {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.94), rgba(20, 184, 166, 0.7));
  color: white;
  font-weight: 900;
  gap: 8px;
  min-height: 44px;
  width: 100%;
}

.task-stack {
  align-content: start;
  display: grid;
  gap: 10px;
  grid-auto-rows: max-content;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.task-row {
  align-items: center;
  background: rgba(4, 16, 31, 0.42);
  border-radius: 8px;
  display: grid;
  gap: 12px;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  min-height: 64px;
  padding: 12px;
}

.task-row.uploading,
.task-row.syncing {
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.2), rgba(4, 16, 31, 0.42));
}

.task-row.failed {
  background: rgba(244, 63, 94, 0.12);
}

.task-icon {
  color: var(--color-brand-cyan);
  display: inline-flex;
}

.task-row.done .task-icon {
  color: var(--color-brand-green);
}

.task-row.failed .task-icon {
  color: var(--color-danger);
}

.task-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.task-copy strong {
  color: var(--color-heading);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-copy small {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 800;
}

.task-copy p,
.drawer-empty {
  color: var(--color-muted);
  font-size: 13px;
  line-height: 1.5;
}

.drawer-empty {
  background: rgba(4, 16, 31, 0.36);
  border-radius: 8px;
  padding: 14px;
}
</style>
