import { defineStore } from "pinia";
import { fetchCurrentUser, logoutUser, refreshCurrentSession } from "../services/auth";
import { createSessionRefresher } from "../services/sessionRefresh";
import { setAccessToken } from "../services/transport";

export const useAuthStore = defineStore("auth", {
  state: () => ({ token: "", user: null, loading: false, hydrated: false, refreshTimer: null, refresher: null }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token && state.user),
    displayName: (state) => state.user?.username || state.user?.email || "未登录",
  },
  actions: {
    setSession(payload) {
      const token = payload?.access_token || "";
      if (!token) throw new Error("登录响应缺少 access_token");
      this.token = token;
      this.user = payload?.user || payload;
      setAccessToken(token);
      this.scheduleRefresh(payload.expires_at);
    },
    setUser(user) { this.user = user; },
    clearSession() {
      this.token = "";
      this.user = null;
      setAccessToken("");
      if (this.refreshTimer) clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    },
    sessionRefresher() {
      if (!this.refresher) {
        this.refresher = createSessionRefresher({
          refresh: refreshCurrentSession,
          onInvalid: () => this.clearSession(),
        });
      }
      return this.refresher;
    },
    async refresh() {
      const session = await this.sessionRefresher().refreshNow();
      this.setSession(session);
      return session;
    },
    scheduleRefresh(expiresAt) {
      if (this.refreshTimer) clearTimeout(this.refreshTimer);
      const delay = Math.max(0, Number(expiresAt) * 1000 - Date.now() - 5 * 60 * 1000);
      this.refreshTimer = setTimeout(() => { void this.refresh(); }, delay);
    },
    async hydrate() {
      if (this.hydrated) return;
      this.loading = true;
      try {
        await this.refresh();
        this.setUser(await fetchCurrentUser());
      } catch (error) {
        if (error?.status !== 401) throw error;
      } finally {
        this.loading = false;
        this.hydrated = true;
      }
    },
    async logoutAction() {
      await logoutUser();
      this.clearSession();
    },
  },
});
