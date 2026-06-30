import { defineStore } from "pinia";
import { syncPlaylist } from "../services/music";

export const usePlaylistStore = defineStore("playlist", {
  state: () => ({
    items: [],
    serverClock: 0,
    syncing: false,
    lastError: "",
  }),
  getters: {
    activeItems: (state) => state.items.filter((item) => item.deleted_at_ms == null),
  },
  actions: {
    async hydrate() {
      await this.sync();
    },
    async sync({ uploads = [] } = {}) {
      this.syncing = true;
      this.lastError = "";
      try {
        const data = await syncPlaylist({ since: this.serverClock, uploads });
        this.serverClock = data.server_clock ?? this.serverClock;
        this.items = Array.isArray(data.changes) ? data.changes : [];
      } finally {
        this.syncing = false;
      }
    },
  },
});
