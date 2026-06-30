import { defineStore } from "pinia";
import { fetchCurrentUser, logoutUser } from "../services/auth";

const TOKEN_KEY = "yts-access-token";
const USER_KEY = "yts-user";

function readStoredUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  return JSON.parse(raw);
}

function writeStoredUser(user) {
  if (!user) {
    localStorage.removeItem(USER_KEY);
    return;
  }
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || "",
    user: readStoredUser(),
    loading: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    displayName: (state) => state.user?.username || state.user?.email || "未登录",
  },
  actions: {
    setSession(payload) {
      this.token = payload?.access_token || payload?.token || "";
      this.user = payload?.user || payload || null;
      if (!this.token) {
        throw new Error("登录响应缺少 access_token");
      }
      localStorage.setItem(TOKEN_KEY, this.token);
      writeStoredUser(this.user);
    },
    setUser(user) {
      this.user = user;
      writeStoredUser(user);
    },
    clearSession() {
      this.token = "";
      this.user = null;
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    },
    async hydrate() {
      if (!this.token) return;
      this.loading = true;
      try {
        const user = await fetchCurrentUser();
        this.setUser(user);
      } catch (err) {
        if (err?.status === 401) {
          this.clearSession();
          return;
        }
        throw err;
      } finally {
        this.loading = false;
      }
    },
    async logoutAction() {
      if (this.token) {
        await logoutUser();
      }
      this.clearSession();
    },
  },
});
