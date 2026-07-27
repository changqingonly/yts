import { defineStore } from "pinia";
import {
  appendPlaylistItems,
  deletePlaylistItem,
  ensureDefaultPlaylist,
  listDeletedPlaylistItems,
  listPlaylistItems,
  listPlaylists,
  reorderPlaylistItems,
  retrySongRendition,
  restorePlaylistItem,
  syncPlaylist,
} from "../services/music";

export const usePlaylistStore = defineStore("playlist", {
  state: () => ({
    playlists: [],
    currentPlaylistId: "",
    playlistItems: [],
    deletedItems: [],
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
      this.playlistItems = normalizePlaylistItems(data.items, "loadItems");
      return this.playlistItems;
    },
    async loadDeletedItems({ playlistId = this.currentPlaylistId } = {}) {
      if (!playlistId) throw new Error("loadDeletedItems requires currentPlaylistId");
      const data = await listDeletedPlaylistItems({ playlistId });
      const playlist = normalizePlaylist(data.playlist);
      this.upsertPlaylist(playlist);
      this.currentPlaylistId = playlist.id;
      this.deletedItems = normalizeDeletedPlaylistItems(data.items, "loadDeletedItems");
      return this.deletedItems;
    },
    async hydrate({ scope = "cloud" } = {}) {
      this.syncing = true;
      this.lastError = "";
      try {
        await this.loadPlaylists({ scope });
        await this.ensureDefault({ scope });
        await this.loadItems();
        await this.loadDeletedItems();
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
        const nextItems = normalizePlaylistItems(data.items, "appendItems");
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
    async deleteItem(itemId) {
      if (!this.currentPlaylistId) throw new Error("deleteItem requires currentPlaylistId");
      if (!itemId) throw new Error("deleteItem requires itemId");
      this.syncing = true;
      this.lastError = "";
      try {
        const data = await deletePlaylistItem({
          playlistId: this.currentPlaylistId,
          itemId,
        });
        const playlist = normalizePlaylist(data.playlist);
        const deletedItem = normalizeDeletedPlaylistItem(data.item);
        this.upsertPlaylist(playlist);
        this.currentPlaylistId = playlist.id;
        this.playlistItems = normalizePlaylistItems(data.items, "deleteItem");
        this.deletedItems = [
          deletedItem,
          ...this.deletedItems.filter((item) => item.id !== deletedItem.id),
        ].sort(compareDeletedPlaylistItems);
        return deletedItem;
      } catch (err) {
        this.lastError = err instanceof Error ? err.message : String(err);
        throw err;
      } finally {
        this.syncing = false;
      }
    },
    async restoreItem(itemId) {
      if (!this.currentPlaylistId) throw new Error("restoreItem requires currentPlaylistId");
      if (!itemId) throw new Error("restoreItem requires itemId");
      this.syncing = true;
      this.lastError = "";
      try {
        const data = await restorePlaylistItem({
          playlistId: this.currentPlaylistId,
          itemId,
        });
        const playlist = normalizePlaylist(data.playlist);
        const restoredItem = normalizePlaylistItem(data.item);
        this.upsertPlaylist(playlist);
        this.currentPlaylistId = playlist.id;
        this.playlistItems = normalizePlaylistItems(data.items, "restoreItem");
        this.deletedItems = this.deletedItems.filter((item) => item.id !== restoredItem.id);
        return restoredItem;
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
      this.playlistItems = normalizePlaylistItems(data.items, "reorder");
      return this.playlistItems;
    },
    async retryRendition(contentHash) {
      if (!contentHash) throw new Error("retryRendition requires contentHash");
      await retrySongRendition({ contentHash });
      return this.loadItems();
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
  if (!VALID_PLAYBACK_STATUSES.has(item.playback_status)) {
    throw new Error("playlist item requires valid playback_status");
  }
  if (!item.rendition_profile) throw new Error("playlist item requires rendition_profile");
  return item;
}

const VALID_PLAYBACK_STATUSES = new Set(["pending", "processing", "ready", "failed"]);

function normalizePlaylistItems(items, source) {
  if (!Array.isArray(items)) throw new Error(`${source} response requires items`);
  return items.map(normalizePlaylistItem);
}

function normalizeDeletedPlaylistItem(item) {
  const normalizedItem = normalizePlaylistItem(item);
  if (normalizedItem.deleted_at_ms == null) {
    throw new Error("deleted playlist item requires deleted_at_ms");
  }
  return normalizedItem;
}

function normalizeDeletedPlaylistItems(items, source) {
  if (!Array.isArray(items)) throw new Error(`${source} response requires items`);
  return items.map(normalizeDeletedPlaylistItem);
}

function compareDeletedPlaylistItems(left, right) {
  return deletedAtMs(right) - deletedAtMs(left);
}

function deletedAtMs(item) {
  const timestamp = Number(item.deleted_at_ms);
  if (!Number.isFinite(timestamp)) {
    throw new Error("deleted playlist item requires numeric deleted_at_ms");
  }
  return timestamp;
}
