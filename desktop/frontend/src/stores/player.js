import { defineStore } from "pinia";
import { getStreamPlayer } from "../audio/streamPlayer";
import { selectedApiTarget } from "../services/http";

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
    setPlaying(isPlaying) {
      this.isPlaying = Boolean(isPlaying);
    },
    setPlaybackClock({ currentTime, duration } = {}) {
      if (currentTime != null) this.currentTime = Math.max(0, Number(currentTime) || 0);
      if (duration != null) this.duration = Math.max(0, Number(duration) || 0);
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
