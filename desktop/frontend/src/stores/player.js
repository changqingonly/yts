import { defineStore } from "pinia";
import { getStreamPlayer } from "../audio/streamPlayer";
import { selectedApiTarget } from "../services/http";
import { ensureInferenceReady } from "../services/inference";

export const usePlayerStore = defineStore("player", {
  state: () => ({
    queue: [],
    currentIndex: 0,
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    // 方案 B:流式生成播放(来源无关,local/cloud 同契约)
    streamState: "idle", // idle | connecting | streaming | done | stopped | error
    streamError: "",
  }),
  getters: {
    currentTrack: (state) => state.queue[state.currentIndex] || null,
    isStreaming: (state) => state.streamState === "connecting" || state.streamState === "streaming",
  },
  actions: {
    async streamGenerate({ prompt, seconds = 8, target = selectedApiTarget(), channels = 2 }) {
      await ensureInferenceReady(target);
      const sp = getStreamPlayer();
      sp.onState = (s) => {
        this.streamState = s;
      };
      sp.onError = (e) => {
        this.streamError = e instanceof Error ? e.message : String(e);
      };
      this.streamError = "";
      await sp.start({ prompt, seconds, target, channels });
    },
    stopStream() {
      getStreamPlayer().stop();
    },
    setQueue(tracks) {
      this.queue = Array.isArray(tracks) ? tracks : [];
      this.currentIndex = 0;
      this.isPlaying = false;
      this.currentTime = 0;
      this.duration = 0;
    },
    setTrackUrl(contentHash, url) {
      if (!contentHash) throw new Error("更新播放地址需要 contentHash");
      if (!url) throw new Error("更新播放地址需要 url");
      if (!this.queue.some((track) => track.contentHash === contentHash)) {
        throw new Error("待更新歌曲不在播放队列中");
      }
      this.queue = this.queue.map((track) =>
        track.contentHash === contentHash ? { ...track, url } : track,
      );
    },
    setPlaying(isPlaying) {
      this.isPlaying = Boolean(isPlaying);
    },
    setPlaybackClock({ currentTime, duration } = {}) {
      if (currentTime != null) this.currentTime = Math.max(0, Number(currentTime) || 0);
      if (duration != null) this.duration = Math.max(0, Number(duration) || 0);
    },
    selectAt(index, { currentTime = 0, isPlaying = false } = {}) {
      if (index < 0 || index >= this.queue.length) {
        throw new Error("播放索引越界");
      }
      const normalizedTime = Number(currentTime);
      if (!Number.isFinite(normalizedTime) || normalizedTime < 0) {
        throw new Error("播放时间必须是非负数字");
      }
      this.currentIndex = index;
      this.isPlaying = Boolean(isPlaying);
      this.currentTime = normalizedTime;
      this.duration = 0;
    },
    playAt(index) {
      if (index < 0 || index >= this.queue.length) {
        throw new Error("播放索引越界");
      }
      this.currentIndex = index;
      this.isPlaying = true;
      this.currentTime = 0;
      this.duration = 0;
    },
    togglePlay() {
      if (!this.currentTrack) {
        throw new Error("播放队列为空");
      }
      this.isPlaying = !this.isPlaying;
    },
  },
});
