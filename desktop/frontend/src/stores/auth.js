import { defineStore } from "pinia";
import { fetchCurrentUser, logoutUser, refreshCurrentSession } from "../services/auth";
import { createSessionRefresher } from "../services/sessionRefresh";
import { setAccessToken, setDeviceId } from "../services/transport";
import { isTauriRuntime } from "../services/environment";
import {
  keychainClear,
  keychainLoad,
  keychainStore,
  vaultClear,
  vaultExists,
  vaultStore,
  vaultUnlock,
} from "../services/desktop";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: "",
    user: null,
    loading: false,
    hydrated: false,
    refreshTimer: null,
    refresher: null,
    // 桌面端登录持久化(cookie 在打包态跨源、跨重启不可靠,详见 App.vue 历史注释):
    // desktopCredentials 是从 Keychain/密码保险库拿到的、用于显式携带的 refresh 凭据。
    desktopCredentials: null,
    persistenceMode: "none", // "none" | "keychain" | "vault" | "unavailable"
    persistenceError: "",
    vaultAvailable: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token && state.user),
    displayName: (state) => state.user?.username || state.user?.email || "未登录",
    needsVaultUnlock: (state) =>
      state.persistenceMode === "unavailable" && state.vaultAvailable && !Boolean(state.token && state.user),
  },
  actions: {
    /** desktopCredentials 变化时同步更新 transport.js 的 device-id 请求头兜底
     * (跨源 cookie 不可靠,X-Yts-Device-Id 头和 yts-device cookie 后端两处都认)。 */
    _setDesktopCredentials(creds) {
      this.desktopCredentials = creds;
      setDeviceId(creds?.deviceId || "");
    },
    setSession(payload) {
      const token = payload?.access_token || "";
      if (!token) throw new Error("登录响应缺少 access_token");
      this.token = token;
      this.user = payload?.user || payload;
      setAccessToken(token);
      this.scheduleRefresh(payload.expires_at);
      if (isTauriRuntime() && payload.refresh_token && payload.device_id) {
        this._setDesktopCredentials({ deviceId: payload.device_id, refreshToken: payload.refresh_token });
        void this.persistDesktopCredentials();
      }
    },
    /** refresh_token 每次调用都会轮换,登录/注册/每次 refresh 后都要重新写入,
     * 否则下次启动时存的还是已经失效的旧 token。Keychain 写入失败是显式错误,不做静默兜底。 */
    async persistDesktopCredentials() {
      if (!this.desktopCredentials) return;
      const { deviceId, refreshToken } = this.desktopCredentials;
      try {
        await keychainStore(deviceId, refreshToken);
        this.persistenceMode = "keychain";
        this.persistenceError = "";
      } catch (err) {
        this.persistenceMode = "unavailable";
        this.persistenceError = err instanceof Error ? err.message : String(err);
      }
    },
    /** 用户在 Keychain 不可用时主动选择的密码保护本地保险库(方案 3,非自动兜底)。 */
    async enableVaultPersistence(passphrase) {
      if (!this.desktopCredentials) throw new Error("没有可保存的登录凭据");
      const { deviceId, refreshToken } = this.desktopCredentials;
      await vaultStore(passphrase, deviceId, refreshToken);
      this.persistenceMode = "vault";
      this.persistenceError = "";
      this.vaultAvailable = true;
    },
    /** 启动时从 Keychain 恢复登录凭据(替代已知在打包态失效的 cookie 静默恢复)。 */
    async restoreDesktopSession() {
      this.vaultAvailable = await vaultExists().catch(() => false);
      let stored = null;
      try {
        stored = await keychainLoad();
        if (stored) this.persistenceMode = "keychain";
      } catch (err) {
        this.persistenceMode = "unavailable";
        this.persistenceError = err instanceof Error ? err.message : String(err);
      }
      if (stored) {
        this._setDesktopCredentials({ deviceId: stored.device_id, refreshToken: stored.refresh_token });
      }
    },
    async unlockVault(passphrase) {
      const stored = await vaultUnlock(passphrase); // 密码错误时 reject("wrong_passphrase")
      this._setDesktopCredentials({ deviceId: stored.device_id, refreshToken: stored.refresh_token });
      this.persistenceMode = "vault";
      return this.refresh();
    },
    setUser(user) {
      this.user = user;
    },
    clearSession() {
      this.token = "";
      this.user = null;
      setAccessToken("");
      if (this.refreshTimer) clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    },
    async clearDesktopPersistence() {
      this._setDesktopCredentials(null);
      this.persistenceMode = "none";
      this.persistenceError = "";
      if (isTauriRuntime()) {
        await keychainClear().catch(() => {});
        await vaultClear().catch(() => {});
        this.vaultAvailable = false;
      }
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
      const creds =
        isTauriRuntime() && this.desktopCredentials
          ? { deviceId: this.desktopCredentials.deviceId, refreshToken: this.desktopCredentials.refreshToken }
          : undefined;
      const session = await this.sessionRefresher().refreshNow(creds);
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
        if (isTauriRuntime()) await this.restoreDesktopSession();
        await this.refresh();
        this.setUser(await fetchCurrentUser());
      } catch (error) {
        // 状态码缺失(云端不可达等网络层失败)和 401 一样按"未登录"处理,静默回落到登录页——
        // 否则打包态一开机若云端暂时连不上,会像本地服务没起来时那样把整个应用卡死在空白页。
        if (error?.status && error.status !== 401) throw error;
      } finally {
        this.loading = false;
        this.hydrated = true;
      }
    },
    async logoutAction() {
      await logoutUser();
      this.clearSession();
      if (isTauriRuntime()) await this.clearDesktopPersistence();
    },
  },
});
