import { defineStore } from "pinia";
import {
  appendPlaylistItems,
  ensureDefaultPlaylist,
  listPlaylistItems,
  listPlaylists,
  reorderPlaylistItems,
  syncPlaylist,
} from "../services/music";

export const usePlaylistStore = defineStore("playlist", {
  state: () => ({
    playlists: [],
    currentPlaylistId: "",
    playlistItems: [],
    serverClock: 0,
    syncing: false,
    lastError: "",
  }),
  getters: {
    currentPlaylist: (state) =>
      state.playlists.find((item) => item.id === state.currentPlaylistId) || null,
    activeItems: (state) => state.playlistItems.filter((item) => item.deleted_at_ms == null),
  },
  actions: {
    async ensureDefault({ scope = "cloud" } = {}) {
      const data = await ensureDefaultPlaylist({ scope });
      const playlist = normalizePlaylist(data.playlist ?? data);
      this.upsertPlaylist(playlist);
      this.currentPlaylistId = playlist.id;
      return playlist;
    },
    async loadPlaylists({ scope } = {}) {
      const data = await listPlaylists({ scope });
      this.playlists = Array.isArray(data.playlists) ? data.playlists.map(normalizePlaylist) : [];
      if (!this.currentPlaylistId && this.playlists.length > 0) {
        this.currentPlaylistId = this.playlists[0].id;
      }
      return this.playlists;
    },
    async loadItems({ playlistId = this.currentPlaylistId } = {}) {
      if (!playlistId) throw new Error("loadItems requires currentPlaylistId");
      const data = await listPlaylistItems({ playlistId });
      const playlist = normalizePlaylist(data.playlist);
      this.upsertPlaylist(playlist);
      this.currentPlaylistId = playlist.id;
      this.playlistItems = Array.isArray(data.items) ? data.items.map(normalizePlaylistItem) : [];
      return this.playlistItems;
    },
    async hydrate({ scope = "cloud" } = {}) {
      this.syncing = true;
      this.lastError = "";
      try {
        await this.loadPlaylists({ scope });
        await this.ensureDefault({ scope });
        await this.loadItems();
      } catch (err) {
        this.lastError = err instanceof Error ? err.message : String(err);
        throw err;
      } finally {
        this.syncing = false;
      }
    },
    async appendItems(items) {
      if (!this.currentPlaylistId) throw new Error("appendItems requires currentPlaylistId");
      this.syncing = true;
      this.lastError = "";
      try {
        const data = await appendPlaylistItems({
          playlistId: this.currentPlaylistId,
          items,
        });
        this.upsertPlaylist(normalizePlaylist(data.playlist));
        const nextItems = Array.isArray(data.items) ? data.items.map(normalizePlaylistItem) : [];
        this.playlistItems = [...this.playlistItems, ...nextItems].sort(
          (left, right) => left.position - right.position,
        );
        return nextItems;
      } catch (err) {
        this.lastError = err instanceof Error ? err.message : String(err);
        throw err;
      } finally {
        this.syncing = false;
      }
    },
    async reorder(orderedItemIds) {
      if (!this.currentPlaylistId) throw new Error("reorder requires currentPlaylistId");
      const data = await reorderPlaylistItems({
        playlistId: this.currentPlaylistId,
        orderedItemIds,
      });
      this.upsertPlaylist(normalizePlaylist(data.playlist));
      this.playlistItems = Array.isArray(data.items) ? data.items.map(normalizePlaylistItem) : [];
      return this.playlistItems;
    },
    async sync({ uploads = [] } = {}) {
      this.syncing = true;
      this.lastError = "";
      try {
        const data = await syncPlaylist({ since: this.serverClock, uploads });
        this.serverClock = data.server_clock ?? this.serverClock;
        this.playlistItems = Array.isArray(data.changes) ? data.changes : [];
      } finally {
        this.syncing = false;
      }
    },
    upsertPlaylist(playlist) {
      const index = this.playlists.findIndex((item) => item.id === playlist.id);
      if (index >= 0) {
        this.playlists.splice(index, 1, playlist);
      } else {
        this.playlists.unshift(playlist);
      }
    },
  },
});

function normalizePlaylist(playlist) {
  if (!playlist?.id) throw new Error("playlist response requires id");
  return {
    ...playlist,
    item_count: Number(playlist.item_count ?? 0),
  };
}

function normalizePlaylistItem(item) {
  if (!item?.id) throw new Error("playlist item response requires id");
  if (!item.content_hash) throw new Error("playlist item requires content_hash");
  if (!item.meta_song) throw new Error("playlist item requires meta_song");
  return item;
}
