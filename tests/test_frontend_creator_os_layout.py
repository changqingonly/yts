from __future__ import annotations

from pathlib import Path

FRONTEND = Path("desktop/frontend/src")
MAIN_SURFACE_FILES = [
    "pages/MusicPage.vue",
    "pages/AssetsPage.vue",
    "pages/SettingsPage.vue",
    "pages/ProfileSetupPage.vue",
    "pages/LoginPage.vue",
    "pages/RegisterPage.vue",
]
BROAD_LIGHT_SURFACES = [
    "background: #ffffff",
    "background: #eef3f7",
    "background: #eef2f6",
    "background: #ecfdf5",
    "background: #fff1f2",
    "background: #e8f0ff",
]


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def read_frontend_file(relative_path: str) -> str:
    return Path("desktop/frontend", relative_path).read_text(encoding="utf-8")


def test_app_shell_router_and_default_music_route_are_defined() -> None:
    app = read_source("App.vue")
    router = read_source("router/index.js")
    main = read_source("main.js")
    shell = read_source("app/AppShell.vue")

    assert "<RouterView />" in app
    assert 'path: "/"' in router
    assert 'redirect: "/music"' in router
    for route in [
        "/music",
        "/studio",
        "/assets",
        "/settings",
        "/profile/setup",
        "/auth/login",
        "/auth/register",
    ]:
        assert route in router
    assert "createPinia()" in main
    assert ".use(router)" in main
    for label in ["音乐", "创作", "资产", "设置"]:
        assert label in shell


def test_main_mounts_immediately_without_a_desktop_backend_health_gate() -> None:
    main = read_source("main.js")

    assert 'import { ensureDesktopDefaultTarget } from "./services/environment";' in main
    assert "ensureDesktopDefaultTarget();" in main
    assert 'createApp(App).use(createPinia()).use(router).mount("#app");' in main
    for token in [
        "waitForDesktopBackend",
        "desktop-startup-gate",
        "DESKTOP_HEALTH_POLL_TIMEOUT_MS",
        "本地服务启动超时",
    ]:
        assert token not in main


def test_environment_store_lazily_starts_local_backend_with_bounded_retry() -> None:
    env_store = read_source("stores/environment.js")

    for token in [
        'import { startGateway, startSidecar } from "../services/desktop";',
        'const shouldRetry = requestTarget === "local" && isTauriRuntime();',
        "void startSidecar().catch(() => {});",
        "void startGateway().catch(() => {});",
        "LOCAL_HEALTH_RETRY_TIMEOUT_MS",
        "LOCAL_HEALTH_RETRY_INTERVAL_MS",
    ]:
        assert token in env_store


def test_music_and_assets_pages_auto_retry_when_local_backend_recovers() -> None:
    for relative_path, load_fn in [
        ("pages/MusicPage.vue", "refreshPlaylist"),
        ("pages/AssetsPage.vue", "loadAssets"),
    ]:
        source = read_source(relative_path)
        assert "() => environment.targetHealth(environment.target)," in source
        assert f'if (status === "online" && error.value) await {load_fn}();' in source


def test_app_shell_sidebar_is_compact_dark_navigation_without_brand_or_user_chrome() -> None:
    shell = read_source("app/AppShell.vue")

    assert "grid-template-columns: 69px minmax(0, 1fr)" in shell
    assert "background: var(--color-sidebar);" in shell
    assert "YTS Studio" not in shell
    assert "Creator OS" not in shell
    assert "creator-user" not in shell
    assert "LogOut" not in shell
    assert "logout()" not in shell


def test_frontend_root_removes_browser_default_margin_for_flush_sidebar() -> None:
    main = read_source("main.js")
    base = read_source("styles/base.css")

    assert 'import "./styles/base.css";' in main
    assert "html," in base
    assert "body," in base
    assert "#app" in base
    assert "height: 100%;" in base
    assert "margin: 0;" in base


def test_frontend_http_unauthorized_clears_session_and_announces_expiry() -> None:
    http = read_source("services/transport.js")

    assert "status === 401" in http
    assert 'setAccessToken("")' in http
    assert 'window.dispatchEvent(new CustomEvent("yts-auth-expired"' in http


def test_app_shell_redirects_to_login_when_auth_expires() -> None:
    shell = read_source("app/AppShell.vue")

    assert 'window.addEventListener("yts-auth-expired", handleAuthExpired)' in shell
    assert 'window.removeEventListener("yts-auth-expired", handleAuthExpired)' in shell
    assert 'router.push({ name: "login", query: { redirect: route.fullPath } })' in shell


def test_auth_store_only_absorbs_unauthorized_hydration_errors() -> None:
    auth = read_source("stores/auth.js")

    # 401(未登录)和网络层失败(云端不可达,error 没有 status)都按"静默回落到登录页"处理——
    # 否则打包态一开机云端连不上,会像本地服务没起来时那样把整个应用卡死在空白页。
    assert "if (error?.status && error.status !== 401) throw error;" in auth
    assert "this.clearSession();" in auth
    assert "onInvalid: () => this.clearSession()" in auth


def test_auth_store_restores_desktop_session_from_keychain_before_refresh() -> None:
    auth = read_source("stores/auth.js")

    for token in [
        'import { isTauriRuntime } from "../services/environment";',
        "async persistDesktopCredentials()",
        "async enableVaultPersistence(passphrase)",
        "async restoreDesktopSession()",
        "async unlockVault(passphrase)",
        "async clearDesktopPersistence()",
        "if (isTauriRuntime()) await this.restoreDesktopSession();",
        "this.persistenceMode = \"unavailable\";",
        "this.persistenceMode = \"keychain\";",
        "this.persistenceMode = \"vault\";",
    ]:
        assert token in auth

    # router.beforeEach(含 auth.hydrate())在 app.use(router) 时立即触发,desktop 会话必须在
    # 第一次 refresh() 之前就从 Keychain 恢复,否则会用一个没有凭据的 cookie-only refresh 顶替。
    assert auth.index("if (isTauriRuntime()) await this.restoreDesktopSession();") < auth.index(
        "await this.refresh();"
    )


def test_auth_service_always_targets_cloud_regardless_of_generation_target() -> None:
    auth = read_source("services/auth.js")

    assert 'const AUTH_TARGET = "cloud";' in auth
    for token in [
        'requestJsonOverHttp("/api/auth/register_key", { auth: false, target: AUTH_TARGET });',
        'requestJsonOverHttp("/api/auth/login_key", { auth: false, target: AUTH_TARGET });',
        "target: AUTH_TARGET,",
    ]:
        assert token in auth
    assert auth.count("target: AUTH_TARGET") >= 5


def test_transport_tags_desktop_requests_for_backend_gating() -> None:
    transport = read_source("services/transport.js")

    assert "isTauriRuntime," in transport
    assert '...(isTauriRuntime() ? { "X-Yts-Client": "desktop" } : {}),' in transport


def test_desktop_service_exposes_keychain_and_vault_commands() -> None:
    desktop = read_source("services/desktop.js")

    for token in [
        'export function keychainLoad() {\n  requireTauri();\n  return invoke("keychain_load");',
        'return invoke("keychain_store", { deviceId, refreshToken });',
        'return invoke("keychain_clear");',
        'return invoke("vault_exists");',
        'return invoke("vault_store", { passphrase, deviceId, refreshToken });',
        'return invoke("vault_unlock", { passphrase });',
        'return invoke("vault_clear");',
    ]:
        assert token in desktop


def test_settings_page_offers_local_password_when_keychain_unavailable() -> None:
    settings = read_source("pages/SettingsPage.vue")

    for token in [
        "auth.persistenceMode === 'unavailable'",
        "async function saveVaultPassphrase()",
        "auth.enableVaultPersistence(vaultPassphrase.value)",
    ]:
        assert token in settings


def test_login_page_offers_vault_unlock_when_needed() -> None:
    login = read_source("pages/LoginPage.vue")

    for token in [
        "const showVaultUnlock = ref(auth.needsVaultUnlock);",
        "const forceAccountLogin = ref(false);",
        "async function submitVaultUnlock()",
        "await auth.unlockVault(vaultPassphrase.value);",
        '"密码错误，请重试"',
        '@click="forceAccountLogin = true"',
    ]:
        assert token in login


def test_frontend_deep_sea_theme_tokens_are_defined() -> None:
    base = read_source("styles/base.css")

    for token in [
        "--color-bg: #071426;",
        "--color-panel: #0c1e33;",
        "--color-panel-strong: #10243a;",
        "--color-border: #1d4265;",
        "--color-text: #d8e7f5;",
        "--color-muted: #8aa4bd;",
        "--color-accent: #0ea5e9;",
    ]:
        assert token in base
    assert "background: var(--color-bg);" in base
    assert "color: var(--color-text);" in base


def test_frontend_uses_subtle_dark_scrollbar_theme() -> None:
    base = read_source("styles/base.css")

    for selector in [
        "*::-webkit-scrollbar",
        "*::-webkit-scrollbar-track",
        "*::-webkit-scrollbar-thumb",
        "*::-webkit-scrollbar-thumb:hover",
        "*::-webkit-scrollbar-corner",
    ]:
        assert selector in base
    assert "scrollbar-width: thin;" in base
    assert "scrollbar-color: rgba(138, 164, 189, 0.34) transparent;" in base
    assert "width: 8px;" in base
    assert "background: transparent;" in base
    assert "background-clip: content-box;" in base
    assert "rgba(14, 165, 233, 0.44)" in base


def test_app_shell_uses_deep_sea_theme_tokens() -> None:
    shell = read_source("app/AppShell.vue")

    for token in [
        "var(--color-bg)",
        "var(--color-sidebar)",
        "var(--color-border-soft)",
        "var(--color-brand-cyan)",
        "var(--color-brand-green)",
    ]:
        assert token in shell


def test_frontend_logo_uses_blue_green_gradient_mark() -> None:
    base = read_source("styles/base.css")
    shell = read_source("app/AppShell.vue")
    creation = read_source("pages/CreationPage.vue")
    favicon = Path("desktop/frontend/public/favicon.svg").read_text(encoding="utf-8")
    index = Path("desktop/frontend/index.html").read_text(encoding="utf-8")

    for token in [
        "--color-brand-cyan: #22d3ee;",
        "--color-brand-green: #34d399;",
        "--color-brand-glow: rgba(45, 212, 191, 0.34);",
    ]:
        assert token in base
    assert "DeepSeaLogo" not in shell
    assert "DeepSeaLogo" not in creation
    assert "components/DeepSeaLogo.vue" not in shell
    assert "components/DeepSeaLogo.vue" not in creation
    assert '<Sparkles :size="27" />' in shell
    assert '<Workflow :size="18" />' in creation
    assert 'id="yts-brand-gradient"' in shell
    assert 'stop-color="var(--color-brand-cyan)"' in shell
    assert 'stop-color="var(--color-brand-green)"' in shell
    assert ".brand-gradient-defs" in shell
    assert ".creator-brand-mark svg" in shell
    assert "stroke: url(#yts-brand-gradient);" in shell
    assert "filter: drop-shadow(0 0 9px var(--color-brand-glow));" in shell
    assert ".brand-mark svg" in creation
    assert "stroke: url(#yts-brand-gradient);" in creation
    assert "filter: drop-shadow(0 0 7px var(--color-brand-glow));" in creation
    assert 'aria-label="乐兔工作室"' in favicon
    assert "brand-spark-large" in favicon
    assert "brand-spark-small" in favicon
    assert "<title>乐兔工作室</title>" in index


def test_app_shell_settings_navigation_lives_at_sidebar_bottom_without_credit_card() -> None:
    shell = read_source("app/AppShell.vue")
    sidebar_rule = shell.split(".creator-sidebar {", 1)[1].split("}", 1)[0]
    bottom_nav_rule = shell.split(".creator-bottom-nav {", 1)[1].split("}", 1)[0]

    assert "const primaryNavItems = [" in shell
    assert 'key: "settings"' not in shell.split("const primaryNavItems = [", 1)[1].split("];", 1)[0]
    assert (
        'const settingsNavItem = { key: "settings", label: "设置", to: "/settings", icon: Settings2 };'
        in shell
    )
    assert 'class="creator-bottom-nav"' in shell
    assert "display: flex;" in sidebar_rule
    assert "flex-direction: column;" in sidebar_rule
    assert "margin-top: auto;" in bottom_nav_rule
    assert "display: grid;" in bottom_nav_rule
    assert "creator-sidebar-card" not in shell
    assert "sidebar-card-label" not in shell
    assert "fetchCreditBalance" not in shell
    assert "fetchDailyUsage" not in shell
    assert "creditBalance" not in shell
    assert "dailyUsage" not in shell
    assert "歌词 {{" not in shell


def test_settings_page_uses_compact_in_page_navigation_and_preserves_control_flow() -> None:
    settings = read_source("pages/SettingsPage.vue")
    template = settings.split("<template>", 1)[1].split("</template>", 1)[0]

    for token in [
        'const activeSection = ref("general");',
        'key: "general"',
        'key: "usage"',
        'key: "account"',
        'aria-label="设置分类"',
        ':aria-current="activeSection === item.key ? \'page\' : undefined"',
        'role="alert"',
        'class="settings-content"',
        'class="usage-progress"',
        '@change="saveModelPreference"',
        'to="/profile/setup"',
        '@click="logout"',
    ]:
        assert token in settings

    assert 'v-if="activeSection === \'general\'"' in template
    assert 'v-else-if="activeSection === \'usage\'"' in template
    assert "v-else" in template
    assert "grid-template-columns: 168px minmax(0, 1fr);" in settings
    assert "grid-template-columns: 1fr;" in settings
    assert "linear-gradient" not in settings
    assert "border-radius: 999px" not in settings
    assert "fetchCreditBalance()" in settings
    assert "fetchCreditLedger()" in settings
    assert "fetchDailyUsage()" in settings
    assert "await auth.logoutAction();" in settings
    assert 'router.push({ name: "login" });' in settings


def test_settings_page_reads_section_query_without_invalid_fallback() -> None:
    settings = read_source("pages/SettingsPage.vue")

    assert 'import { RouterLink, useRoute, useRouter } from "vue-router";' in settings
    assert "const route = useRoute();" in settings
    assert "function sectionFromQuery(value)" in settings
    assert 'return "general";' in settings
    assert 'throw new Error(`未知设置分类: ${String(value)}`);' in settings
    assert "watch(" in settings
    assert "() => route.query.section" in settings
    assert "activeSection.value = sectionFromQuery(section);" in settings
    assert "error.value = err instanceof Error ? err.message : String(err);" in settings


def test_settings_surfaces_keep_grid_rows_top_aligned_across_tabs() -> None:
    settings = read_source("pages/SettingsPage.vue")
    profile = read_source("pages/ProfileSetupPage.vue")
    settings_page_rule = settings.split(".settings-page {", 1)[1].split("}", 1)[0]
    profile_page_rule = profile.split(".profile-page {", 1)[1].split("}", 1)[0]

    assert "align-content: start;" in settings_page_rule
    assert "align-content: start;" in profile_page_rule


def test_profile_settings_integrates_navigation_form_and_explicit_async_errors() -> None:
    profile = read_source("pages/ProfileSetupPage.vue")

    for token in [
        'to="/settings"',
        ':to="{ path: \'/settings\', query: { section: \'usage\' } }"',
        'aria-current="page"',
        'form="profile-form"',
        'id="profile-form"',
        'role="alert"',
        'role="status"',
        "const profileLoading = ref(true);",
        "const profileReady = ref(false);",
        "const avatarUploading = ref(false);",
        "profileReady.value = true;",
        "!profileReady.value",
        "profileLoading.value = false;",
        "avatarUploading.value = true;",
        "avatarUploading.value = false;",
        "await fetchProfile();",
        "await uploadAvatar(dataUrl);",
        "await updateProfile({",
    ]:
        assert token in profile


def test_profile_avatar_preview_uses_current_api_origin() -> None:
    profile = read_source("pages/ProfileSetupPage.vue")
    transport = read_source("services/transport.js")

    assert "export function apiResourceUrl(path" in transport
    assert "new URL(path, `${apiBase(target)}/`).toString()" in transport
    assert 'import { apiResourceUrl } from "../services/transport";' in profile
    assert "const avatarPreviewUrl = computed(() =>" in profile
    assert 'v-if="avatarPreviewUrl" :src="avatarPreviewUrl"' in profile

    assert profile.count("catch (err)") >= 3
    assert profile.count("error.value = err instanceof Error ? err.message : String(err);") >= 3
    assert "grid-template-columns: 168px minmax(0, 1fr);" in profile
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in profile
    assert "grid-template-columns: 1fr;" in profile
    assert "linear-gradient" not in profile


def test_app_shell_api_target_switch_lives_above_settings_navigation() -> None:
    shell = read_source("app/AppShell.vue")
    bottom_nav_block = shell.split('<nav class="creator-bottom-nav"', 1)[1].split("</nav>", 1)[0]

    assert 'import { useEnvironmentStore } from "../stores/environment";' in shell
    assert "const environment = useEnvironmentStore();" in shell
    assert "environment.options" in shell
    assert "environment.target" in shell
    assert "environment.setTarget(item.value)" in shell
    assert "void environment.checkHealth(environment.target)" in shell
    assert "void environment.checkHealth(item.value);" in shell
    assert "environment.checkAllHealth()" not in shell
    assert "environment.targetHealth(item.value)" in shell
    assert 'class="global-target-switch"' in bottom_nav_block
    assert 'aria-label="API 环境"' in bottom_nav_block
    assert 'v-for="item in environment.options"' in bottom_nav_block
    assert ':disabled="environment.switchLocked"' in bottom_nav_block
    assert '@click="switchEnvironmentTarget(item)"' in bottom_nav_block
    assert "target-status-dot" in bottom_nav_block
    assert 'class="target-lock-note"' in bottom_nav_block
    assert bottom_nav_block.index('class="global-target-switch"') < bottom_nav_block.index(
        ':to="settingsNavItem.to"'
    )


def test_app_shell_api_target_switch_only_renders_on_desktop() -> None:
    shell = read_source("app/AppShell.vue")
    bottom_nav_block = shell.split('<nav class="creator-bottom-nav"', 1)[1].split("</nav>", 1)[0]

    # Web 版只有云端模式,本地/云端切换只对 Desktop(Tauri)有意义。
    assert 'import { isTauriRuntime } from "../services/environment";' in shell
    assert 'v-if="isTauriRuntime()" class="global-target-switch"' in bottom_nav_block


def test_app_shell_api_target_switch_only_highlights_selected_button() -> None:
    shell = read_source("app/AppShell.vue")
    switch_rule = shell.split(".global-target-switch {", 1)[1].split("}", 1)[0]
    button_rule = shell.split(".global-target-switch button {", 1)[1].split("}", 1)[0]
    active_rule = shell.split(".global-target-switch button.active {", 1)[1].split("}", 1)[0]

    assert "background: transparent;" in switch_rule
    assert "background: transparent;" in button_rule
    assert "background: rgba(14, 165, 233, 0.28);" in active_rule
    assert "box-shadow:" in active_rule


def test_app_shell_active_navigation_has_no_outer_accent_border() -> None:
    shell = read_source("app/AppShell.vue")
    active_rule = shell.split(".creator-nav-item:hover,\n.creator-nav-item.active {", 1)[1].split(
        "}", 1
    )[0]

    assert "border: 1px solid transparent;" in shell
    assert "border-color: var(--color-accent);" not in active_rule


def test_app_shell_sidebar_stays_above_overflowing_page_surfaces() -> None:
    shell = read_source("app/AppShell.vue")
    sidebar_rule = shell.split(".creator-sidebar {", 1)[1].split("}", 1)[0]
    main_rule = shell.split(".creator-main {", 1)[1].split("}", 1)[0]

    assert "position: relative;" in sidebar_rule
    assert "z-index: 50;" in sidebar_rule
    assert "position: relative;" in main_rule
    assert "z-index: 0;" in main_rule


def test_app_shell_logo_has_no_outer_frame_background_and_larger_mark() -> None:
    shell = read_source("app/AppShell.vue")
    brand_rule = shell.split(".creator-brand-mark {", 1)[1].split("}", 1)[0]

    assert '<Sparkles :size="27" />' in shell
    assert "background:" not in brand_rule
    assert "box-shadow" not in brand_rule


def test_main_pages_do_not_keep_broad_light_surfaces() -> None:
    for relative_path in MAIN_SURFACE_FILES:
        source = read_source(relative_path)
        for color in BROAD_LIGHT_SURFACES:
            assert color not in source, f"{relative_path} still contains {color}"


def test_music_stream_generation_uses_global_api_target() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("stores/player.js")
    stream_player = read_source("audio/streamPlayer.js")
    environment = read_source("services/environment.js")
    transport = read_source("services/transport.js")

    assert "selectedApiTarget" in music
    assert "selectedApiTarget()" in music
    assert "streamTarget" not in music
    assert '<select v-model="streamTarget"' not in music
    assert 'target = "local"' not in player
    assert "target = selectedApiTarget()" in player
    assert "currentAccessToken" in stream_player
    assert "openBinaryStream" in stream_player
    assert 'authorization: token ? `Bearer ${token}` : ""' in stream_player
    assert 'openBinaryStream("", {' in stream_player
    assert "streamEndpointForTarget(target)" in transport
    assert "const WS_BASES = {" not in stream_player
    assert "musicWsBase" in environment
    assert "throw new Error(`Unsupported API target: ${target}`);" in environment
    assert "WS_BASES[target] || WS_BASES.local" not in stream_player


def test_music_service_uses_playlist_and_song_upload_contracts() -> None:
    service = read_source("services/music.js")
    store = read_source("stores/playlist.js")
    transport = read_source("services/transport.js")

    for token in [
        "uploadSong",
        'uploadForm("/api/music/upload"',
        "loadSongObjectUrl",
        "requestBlob(`/api/music/file/${contentHash}`",
        "listPlaylists",
        "requestJson(`/api/music/playlists",
        "ensureDefaultPlaylist",
        'requestJson("/api/music/playlists/default"',
        "appendPlaylistItems",
        "requestJson(`/api/music/playlists/${playlistId}/items`",
        "reorderPlaylistItems",
        "requestJson(`/api/music/playlists/${playlistId}/items/reorder`",
        "listDeletedPlaylistItems",
        "requestJson(`/api/music/playlists/${playlistId}/items/deleted`",
        "deletePlaylistItem",
        "requestJson(`/api/music/playlists/${playlistId}/items/${itemId}`",
        "restorePlaylistItem",
        "requestJson(`/api/music/playlists/${playlistId}/items/${itemId}/restore`",
    ]:
        assert token in service
    assert "uploadLocalImport" not in service
    assert "/api/music/local_import/upload" not in service

    for token in [
        "playlists: []",
        "currentPlaylistId",
        "playlistItems",
        "ensureDefault",
        "loadItems",
        "appendItems",
        "deletedItems",
        "loadDeletedItems",
        "deleteItem",
        "restoreItem",
        "item_count",
        "meta_song",
    ]:
        assert token in store

    assert "export async function requestBlob(path, options = {})" in transport
    assert "Authorization: `Bearer ${token}`" in transport
    assert "URL.createObjectURL(blob)" in service


def test_music_page_loads_authenticated_audio_blob_urls_before_queueing() -> None:
    music = read_source("pages/MusicPage.vue")

    assert 'import { loadSongObjectUrl } from "../services/music";' in music
    assert "const trackUrlByHash = ref(new Map());" in music
    assert "await loadPlayableTrackUrls(playlist.activeItems);" in music
    assert "player.setQueue(tracks.value);" in music
    assert music.index("await loadPlayableTrackUrls(playlist.activeItems);") < music.index(
        "player.setQueue(tracks.value);"
    )
    assert "URL.revokeObjectURL" in music
    assert "`/api/music/file/${encodeURIComponent(item.content_hash)}`" not in music


def test_music_import_drawer_supports_batch_status_and_capacity_warning() -> None:
    drawer = read_source("components/MusicImportDrawer.vue")
    for token in [
        "导入本地歌曲",
        "将导入到",
        "currentTargetLabel",
        "最多 2000 首",
        "remainingCapacity",
        "queued",
        "uploading",
        "uploaded",
        "syncing",
        "done",
        "failed",
        "retryImport",
        "uploadSong",
        "appendItems",
        "multiple",
    ]:
        assert token in drawer

    assert ".task-stack {" in drawer
    assert "align-content: start;" in drawer
    assert "grid-auto-rows: max-content;" in drawer


def test_music_import_drawer_lists_existing_imports_by_recent_added_time() -> None:
    drawer = read_source("components/MusicImportDrawer.vue")
    template = drawer.split("<template>", 1)[1].split("</template>", 1)[0]
    script = drawer.split("<script setup>", 1)[1].split("</script>", 1)[0]

    assert "const importHistoryItems = computed(() =>" in script
    assert "[...playlist.activeItems].sort" in script
    assert "importTimestamp(right) - importTimestamp(left)" in script
    assert "function importTimestamp(item)" in script
    assert 'throw new Error("playlist item requires added_at_ms")' in script
    assert "function itemImportTimeLabel(item)" in script

    assert 'class="import-history"' in template
    assert 'aria-label="已导入歌曲"' in template
    assert "已导入歌曲" in template
    assert "最近导入在前" in template
    assert 'v-for="item in importHistoryItems"' in template
    assert "{{ itemTitle(item) }}" in template
    assert "{{ itemArtist(item) }} · {{ itemImportTimeLabel(item) }}" in template
    assert "暂无已导入歌曲" in template
    assert template.index('class="import-history"') < template.index('class="task-stack"')

    assert (
        "grid-template-rows: auto auto auto minmax(150px, 0.78fr) minmax(120px, 0.72fr);" in drawer
    )
    assert ".history-list {" in drawer
    assert ".history-row {" in drawer


def test_music_import_history_rows_match_playlist_and_history_item_style() -> None:
    music = read_source("pages/MusicPage.vue")
    drawer = read_source("components/MusicImportDrawer.vue")
    template = drawer.split("<template>", 1)[1].split("</template>", 1)[0]
    history_row_block = template.split('class="history-row"', 1)[1].split("</article>", 1)[0]
    playlist_row_rule = music.split(".drawer-row {", 1)[1].split("}", 1)[0]
    import_row_rule = drawer.split(".history-row {", 1)[1].split("}", 1)[0]
    import_icon_rule = drawer.split(".history-icon {", 1)[1].split("}", 1)[0]
    import_title_rule = drawer.split(".history-row strong {", 1)[1].split("}", 1)[0]
    import_meta_rule = drawer.split(".history-row small {", 1)[1].split("}", 1)[0]
    task_row_rule = drawer.split(".task-row {", 1)[1].split("}", 1)[0]
    task_icon_rule = drawer.split(".task-icon {", 1)[1].split("}", 1)[0]
    task_title_rule = drawer.split(".task-title {", 1)[1].split("}", 1)[0]
    task_state_rule = drawer.split(".task-state {", 1)[1].split("}", 1)[0]

    assert '<span class="history-icon">' in history_row_block
    assert "{{ itemTitle(item) }}" in history_row_block
    assert "{{ itemArtist(item) }} · {{ itemImportTimeLabel(item) }}" in history_row_block
    assert 'class="history-copy"' not in template

    for token in [
        "background: rgba(4, 16, 31, 0.3);",
        "border: 0;",
        "border-radius: 6px;",
        "box-sizing: border-box;",
        "color: var(--color-text);",
        "display: grid;",
        "font: inherit;",
        "align-items: center;",
        "gap: 6px;",
        "grid-template-columns: 24px minmax(0, 1fr) minmax(48px, 78px);",
        "min-height: 34px;",
        "padding: 5px 8px;",
        "width: 100%;",
    ]:
        assert token in playlist_row_rule
        assert token in import_row_rule
        assert token in task_row_rule

    assert "color: var(--color-muted);" in import_icon_rule
    assert "font-size: 11px;" in import_icon_rule
    assert "line-height: 1;" in import_icon_rule
    assert "font-size: 12px;" in import_title_rule
    assert "line-height: 1.1;" in import_title_rule
    assert "font-size: 11px;" in import_meta_rule
    assert "font-size: 13px;" not in import_title_rule
    assert "justify-self: end;" in import_meta_rule
    assert "line-height: 1;" in import_meta_rule
    for token in [
        "color: var(--color-muted);",
        "display: inline-flex;",
        "font-size: 11px;",
        "line-height: 1;",
    ]:
        assert token in task_icon_rule
    for token in [
        "color: var(--color-heading);",
        "font-size: 12px;",
        "line-height: 1.1;",
        "overflow: hidden;",
        "text-overflow: ellipsis;",
        "white-space: nowrap;",
    ]:
        assert token in task_title_rule
    assert "justify-self: end;" in task_state_rule
    assert "min-width: 0;" in task_state_rule
    assert 'class="task-state"' in template
    assert "task.error || statusLabels[task.status]" in template


def test_music_page_uses_import_drawer_and_meta_song_tracks() -> None:
    music = read_source("pages/MusicPage.vue")
    for token in [
        "MusicImportDrawer",
        "importDrawerOpen",
        '@click="importDrawerOpen = true"',
        ':open="importDrawerOpen"',
        '@close="importDrawerOpen = false"',
        "playlist.hydrate",
        "item.title_alias",
        "item.meta_song",
        "playableTrackUrl(item)",
    ]:
        assert token in music
    assert "uploadLocalImport" not in music
    assert "onImportFile" not in music


def test_music_page_formats_playlist_load_errors_with_environment_and_endpoint() -> None:
    music = read_source("pages/MusicPage.vue")
    transport = read_source("services/transport.js")

    assert 'import { apiBase, selectedApiTarget } from "../services/http";' in music
    assert "function formatMusicLoadError(err)" in music
    assert "播放列表加载失败" in music
    assert "apiBase(environment.target)" in music
    assert "err.path" in music
    assert "err?.status === 404" in music
    assert "当前环境" in music
    assert "不是播放器布局错误" in music
    assert "error.value = formatMusicLoadError(err);" in music
    assert "error.path = path;" in transport
    assert "error.target = target;" in transport
    assert "error.apiBase = baseUrl;" in transport


def test_music_progress_copy_does_not_duplicate_loop_mode_label() -> None:
    player = read_source("components/YtsAudioPlayer.vue")
    mode_button_block = player.split('<button class="mode-button"', 1)[1].split("</button>", 1)[0]

    assert 'class="progress-copy"' not in player
    assert "loopLabel" in mode_button_block


def test_audio_player_uses_centered_time_progress_and_full_width_scrubber() -> None:
    player = read_source("components/YtsAudioPlayer.vue")
    template = player.split("<template>", 1)[1].split("</template>", 1)[0]
    timeline_block = template.split('<div class="timeline-row"', 1)[1].split(
        "</media-time-range>", 1
    )[0]
    controller_block = template.split("<media-controller", 1)[1].split("</media-controller>", 1)[0]

    assert "currentTimeLabel" in player
    assert "durationLabel" in player
    assert "timelineProgress" in player
    assert "timelineLabelPlacement" in player
    assert "--timeline-progress" in template
    assert 'id="yts-audio-controller"' in template
    assert ':class="[' in template
    assert "'time-progress'" in template
    assert "timelineLabelPlacement" in template
    assert "{{ currentTimeLabel }}/{{ durationLabel }}" in timeline_block
    assert "时间进度：" not in template
    assert 'class="timeline-row"' not in controller_block
    assert 'class="media-controls"' not in controller_block
    assert 'mediacontroller="yts-audio-controller"' in timeline_block
    assert timeline_block.index("'time-progress'") < timeline_block.index("<media-time-range")
    assert "<media-time-range" in timeline_block
    assert "<media-time-display" not in timeline_block
    assert "<media-duration-display" not in timeline_block
    assert "grid-template-rows: auto auto;" in player
    assert "grid-template-rows: minmax(220px, 1fr) auto auto;" not in player
    assert "grid-template-columns: minmax(0, 1fr);" in player
    assert "left: var(--timeline-progress);" in player
    assert "transform: translate(-50%, -100%);" in player
    assert ".time-progress.edge-start" in player
    assert "left: 0;" in player.split(".time-progress.edge-start {", 1)[1].split("}", 1)[0]
    assert (
        "transform: translateY(-100%);"
        in player.split(".time-progress.edge-start {", 1)[1].split("}", 1)[0]
    )
    assert ".time-progress.edge-end" in player
    assert "right: 0;" in player.split(".time-progress.edge-end {", 1)[1].split("}", 1)[0]
    assert (
        "transform: translateY(-100%);"
        in player.split(".time-progress.edge-end {", 1)[1].split("}", 1)[0]
    )
    assert "--media-control-background: transparent;" in player
    assert "--media-range-padding-left: 0px;" in player
    assert "--media-range-padding-right: 0px;" in player
    assert "--media-range-track-height: 2px;" in player
    assert "--media-range-track-background: rgba(216, 231, 245, 0.28);" in player


def test_audio_player_removes_wavesurfer_visual_rendering_after_butterchurn() -> None:
    package_json = read_frontend_file("package.json")
    player = read_source("components/YtsAudioPlayer.vue")
    template = player.split("<template>", 1)[1].split("</template>", 1)[0]

    assert ':class="{ empty: !sourceUrl, playing }"' in player
    assert '"wavesurfer.js"' not in package_json
    assert 'import WaveSurfer from "wavesurfer.js";' not in player
    assert "WaveSurfer.create" not in player
    assert "waveformRef" not in player
    assert "requireWave" not in player
    assert 'class="hero-wave"' not in template
    assert 'class="waveform-canvas"' not in template
    assert "shadow-root" not in player
    assert ".yts-audio-player.playing .waveform-canvas" not in player
    assert "@keyframes waveform-breathe" not in player
    assert "drop-shadow(0 0 14px" not in player
    assert "progressColor" not in player
    assert "waveColor" not in player
    assert "player-spacer" not in player


def test_audio_player_does_not_reserve_removed_waveform_stage_height() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")
    template = player.split("<template>", 1)[1].split("</template>", 1)[0]
    root_rule = player.split(".yts-audio-player {", 1)[1].split("}", 1)[0]
    stage_rule = music.split(".player-stage {", 1)[1].split("}", 1)[0]

    assert 'class="player-spacer"' not in template
    assert "height: 100%;" not in root_rule
    assert "grid-template-rows: auto auto;" in root_rule
    assert "minmax(220px, 1fr)" not in root_rule
    assert "align-content: end;" in stage_rule
    assert "grid-template-rows: auto;" in stage_rule


def test_audio_player_formats_media_errors_without_object_string() -> None:
    player = read_source("components/YtsAudioPlayer.vue")
    template = player.split("<template>", 1)[1].split("</template>", 1)[0]
    audio_block = template.split("<audio", 1)[1].split("></audio>", 1)[0]

    assert "function formatPlaybackError(err)" in player
    assert "MEDIA_ERROR_MESSAGES" in player
    assert "音频加载失败" in player
    assert ':src="sourceUrl || undefined"' not in audio_block
    assert ':src="sourceUrl"' not in audio_block
    assert "player.src = nextSourceUrl;" in player
    assert "player.load();" in player
    assert '@error="handleAudioElementError"' in audio_block
    assert "function handleAudioElementError(event)" in player
    assert 'emit("play-error", formatPlaybackError(event));' in player
    assert 'wave.value.on("error", handleWaveError)' not in player
    assert "function handleWaveError(err)" not in player
    assert "function isSourceAbort(err)" not in player
    assert 'err?.name === "AbortError"' not in player
    assert "function extractNativeMediaError(err)" in player
    assert "err.code >= 1 && err.code <= 4" in player
    assert "err?.target?.error || err" not in player


def test_music_player_places_track_identity_inside_open_source_player_shell() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")
    assert 'class="control-row"' in player
    control_row_block = player.split('<div class="control-row"', 1)[1].split(
        "</media-control-bar>", 1
    )[0]

    assert 'class="player-meta"' not in music
    assert 'class="transport-bar"' not in music
    assert 'class="track-summary"' in player
    assert ':track="currentTrack"' in music
    assert "trackTitle" in player
    assert "trackArtist" in player
    assert player.index('class="timeline-row"') < player.index('class="control-row"')
    assert 'class="track-summary"' in control_row_block
    assert control_row_block.index('class="track-summary"') < control_row_block.index(
        'class="button-groups"'
    )


def test_music_player_uses_open_source_media_components_instead_of_hand_rolled_controls() -> None:
    package_json = read_frontend_file("package.json")
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")

    assert '"media-chrome"' in package_json
    assert '"wavesurfer.js"' not in package_json
    assert 'import "media-chrome";' in player
    assert 'import WaveSurfer from "wavesurfer.js";' not in player
    for custom_element in [
        "<media-controller",
        "<media-play-button",
        "<media-time-range",
        "<media-mute-button",
        "<media-volume-range",
    ]:
        assert custom_element in player
    assert "'time-progress'" in player
    assert "<media-time-display" not in player.split("<template>", 1)[1].split("</template>", 1)[0]
    assert (
        "<media-duration-display" not in player.split("<template>", 1)[1].split("</template>", 1)[0]
    )
    assert 'ref="audioRef"' in player
    assert 'ref="waveformRef"' not in player
    assert "WaveSurfer.create" not in player
    assert ':src="sourceUrl"' not in player
    assert "player.src = nextSourceUrl;" in player
    assert "function syncPlaybackIntent()" in player
    assert "const player = requireAudio();" in player
    assert "await player.play();" in player
    assert "YtsAudioPlayer" in music
    assert "<YtsAudioPlayer" in music
    for hand_rolled_token in [
        "waveBars",
        "progressPercent",
        "elapsedSeconds",
        "totalSeconds",
        "waveform-rail",
        "compact-controls",
        "primary-play",
        "progress-track",
        "waveBreath",
    ]:
        assert hand_rolled_token not in music


def test_music_player_control_layout_uses_timeline_row_then_track_left_and_controls_right() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")
    root_rule = player.split(".yts-audio-player {", 1)[1].split("}", 1)[0]
    controls_rule = player.split(".media-controls {", 1)[1].split("}", 1)[0]
    timeline_rule = player.split(".timeline-row {", 1)[1].split("}", 1)[0]
    control_button_rule = player.split(".transport-button,\n.mode-button {", 1)[1].split("}", 1)[0]
    controller_block = player.split("<media-controller", 1)[1].split("</media-controller>", 1)[0]
    assert 'class="timeline-row"' in player
    assert 'class="control-row"' in player
    assert 'class="button-groups"' in player
    timeline_row_block = player.split('<div class="timeline-row"', 1)[1].split(
        "</media-time-range>", 1
    )[0]
    control_row_block = player.split('<div class="control-row"', 1)[1].split(
        "</media-control-bar>", 1
    )[0]
    control_row_rule = player.split(".control-row {", 1)[1].split("}", 1)[0]
    button_groups_rule = player.split(".button-groups {", 1)[1].split("}", 1)[0]
    track_rule = player.split(".track-summary {", 1)[1].split("}", 1)[0]
    artist_rule = player.split(".track-summary small {", 1)[1].split("}", 1)[0]

    for class_name in [
        "timeline-row",
        "control-row",
        "track-summary",
        "button-groups",
        "transport-group",
        "utility-group",
    ]:
        assert class_name in player
    assert 'class="timeline-row"' not in controller_block
    assert 'class="control-row"' not in controller_block
    assert 'class="media-controls"' not in controller_block
    assert player.index('class="timeline-row"') < player.index('class="control-row"')
    assert timeline_row_block.index("'time-progress'") < timeline_row_block.index(
        "<media-time-range"
    )
    assert '<media-time-range mediacontroller="yts-audio-controller"' in timeline_row_block
    assert "<media-time-display" not in timeline_row_block
    assert "<media-duration-display" not in timeline_row_block
    assert "transport-group" not in timeline_row_block
    assert "utility-group" not in timeline_row_block
    assert 'class="track-summary"' in control_row_block
    assert 'class="button-groups"' in control_row_block
    assert control_row_block.index('class="track-summary"') < control_row_block.index(
        'class="button-groups"'
    )
    assert 'class="transport-group"' in control_row_block
    assert 'class="utility-group"' in control_row_block
    assert "<ListMusic" not in player
    assert '"queue"' not in player
    assert '@queue="showDrawer' not in music
    assert "grid-template-rows: auto auto;" in root_rule
    assert "height: 100%;" not in root_rule
    assert "min-width: 0;" in root_rule
    assert "display: block;" in controls_rule
    assert "max-width: none;" in controls_rule
    assert "margin-inline: auto;" in controls_rule
    assert "width: 100%;" not in controls_rule
    stage_rule = music.split(".player-stage {", 1)[1].split("}", 1)[0]
    assert "--shell-sidebar-width: 69px;" in stage_rule
    assert "--stage-left-inset: 28px;" in stage_rule
    assert "align-content: end;" in stage_rule
    assert "grid-template-rows: auto;" in stage_rule
    assert "overflow: visible;" in stage_rule
    assert (
        "margin-left: calc(0px - var(--stage-x-pad, 0px) - var(--stage-left-inset));"
        in timeline_rule
    )
    assert "margin-right: 0;" in timeline_rule
    assert "width: calc(100vw - var(--shell-sidebar-width));" in timeline_rule
    assert "grid-template-columns: minmax(180px, 1fr) max-content;" in control_row_rule
    assert "justify-content: end;" in button_groups_rule
    assert "border: 0;" in control_button_rule
    assert "border: 1px" not in control_button_rule
    assert "justify-items: start;" in track_rule
    assert "line-height: 1.2;" in track_rule
    assert "line-height: 1.2;" in artist_rule


def test_creation_page_uses_dark_theme_instead_of_broad_light_surfaces() -> None:
    source = read_source("pages/CreationPage.vue")

    for token in [
        "var(--color-bg)",
        "var(--color-panel)",
        "var(--color-text)",
        "var(--color-accent)",
    ]:
        assert token in source
    for color in BROAD_LIGHT_SURFACES:
        assert color not in source


def test_creation_page_uses_deep_sea_studio_branding() -> None:
    source = read_source("pages/CreationPage.vue")

    assert "乐兔工作室" in source
    assert "制作流程" in source
    assert "YTS Studio" not in source


def test_creation_page_prioritizes_creator_session_feed() -> None:
    source = read_source("pages/CreationPage.vue")
    template = source.split("<template>", 1)[1].split("</template>", 1)[0]

    for token in [
        'class="creation-session-sidebar"',
        'class="creation-feed"',
        'class="creator-composer"',
        'class="creator-progress"',
        'class="completed-work"',
        'const pageMode = ref("creator");',
        "const creatorProgressStages = computed(() =>",
        '@click="startNewCreation"',
        '@click="applyInspiration(item.prompt)"',
        ':disabled="!prompt.trim() || isWorkflowBusy"',
        'const prompt = ref("");',
    ]:
        assert token in source

    creator = template.split('v-if="pageMode === \'creator\'"', 1)[1].split(
        'v-else class="advanced-workspace"', 1
    )[0]
    for technical_token in ["root id", "span id", "LLM 输入", "配置 JSON", "VueFlow"]:
        assert technical_token not in creator


def test_creation_page_uses_compose_first_empty_state_without_duplicate_navigation() -> None:
    source = read_source("pages/CreationPage.vue")
    template = source.split("<template>", 1)[1].split("</template>", 1)[0]
    creator = template.split('v-if="pageMode === \'creator\'"', 1)[1].split(
        'v-else class="advanced-workspace"', 1
    )[0]

    for token in [
        ":class=\"['creator-conversation', { 'is-empty': !hasRunStarted, 'is-completed': Boolean(finalDelivery) }]\"",
        'v-if="!hasRunStarted" class="empty-composer-intro"',
        'v-if="hasRunStarted" class="creation-feed"',
        ':class="[\'composer-dock\', { \'is-empty\': !hasRunStarted }]"',
        '<span class="composer-mode" title="当前创作模式">',
    ]:
        assert token in creator

    assert 'class="creator-history-button"' not in creator
    assert "LYRICS MANUSCRIPT" not in creator
    assert "ChevronDown" not in creator
    inspirations = source.split("const inspirationItems = [", 1)[1].split("];", 1)[0]
    assert inspirations.count("prompt: ") == 3

    creator_mode_rule = source.split(".creator-mode {", 1)[1].split("}", 1)[0]
    session_sidebar_rule = source.split(".creation-session-sidebar {", 1)[1].split("}", 1)[0]
    composer_rule = source.split(".creator-composer {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: 208px minmax(0, 1fr);" in creator_mode_rule
    assert "radial-gradient" not in creator_mode_rule
    assert "display: flex;" in session_sidebar_rule
    assert "flex-direction: column;" in session_sidebar_rule
    session_list_rule = source.split(".session-list {", 1)[1].split("}", 1)[0]
    assert "flex: 1 1 auto;" in session_list_rule
    assert "max-width: 720px;" in composer_rule


def test_creation_page_maps_real_nodes_to_five_creator_progress_stages() -> None:
    source = read_source("pages/CreationPage.vue")

    for stage_id in ["understand", "compose", "write", "polish", "complete"]:
        assert f'id: "{stage_id}"' in source
    assert "nodeStatus(nodeId)" in source
    assert "`stage-${stage.status}`" in source
    for status in ["active", "completed", "waiting"]:
        assert f'stageStatus = "{status}"' in source


def test_creation_page_focuses_running_state_without_duplicate_status_dock() -> None:
    source = read_source("pages/CreationPage.vue")
    template = source.split("<template>", 1)[1].split("</template>", 1)[0]
    creator = template.split('v-if="pageMode === \'creator\'"', 1)[1].split(
        'v-else class="advanced-workspace"', 1
    )[0]

    for token in [
        'class="manuscript-quote"',
        'v-if="activeCreatorStage" class="progress-summary"',
        "{{ activeCreatorStageNumber }}/5",
        "v-if=\"!hasRunStarted && !isWorkflowExecuting\" :class=\"['composer-dock'",
        'aria-live="polite"',
        '@click="startNewCreation"',
    ]:
        assert token in creator

    assert "const activeCreatorStageNumber = computed(() =>" in source
    assert "completedCount }}/{{ draftTemplate?.nodes.length" not in creator
    assert 'class="creator-composer"' in creator.split(
        'v-if="!hasRunStarted && !isWorkflowExecuting"', 1
    )[1]
    assert 'class="run-status-dock"' not in creator
    assert 'class="run-status-content"' not in creator


def test_creation_page_collapses_creator_sidebar_and_drawer_on_narrow_screens() -> None:
    source = read_source("pages/CreationPage.vue")
    responsive = source.split("@media (max-width: 900px) {", 1)[1].split(
        "@media (prefers-reduced-motion", 1
    )[0]

    assert ".creation-session-sidebar" in responsive
    assert "display: none;" in responsive
    assert "grid-template-columns: minmax(0, 1fr);" in source
    assert ".completed-work-head" in responsive
    assert "flex-direction: column;" in source.split(".completed-work-head {", 2)[2].split("}", 1)[0]


def test_creation_page_shows_one_concise_user_facing_error_message() -> None:
    source = read_source("pages/CreationPage.vue")

    assert "const displayError = computed(() => formatUserError(error.value));" in source
    assert "function formatUserError(rawError)" in source
    assert "OpenAI 接口请求失败" in source
    assert "API Base URL" in source
    assert 'v-if="displayError"' in source
    assert source.count('class="error-box compact-error"') == 1
    assert '<pre v-if="error" class="error-box">{{ error }}</pre>' not in source
    assert "{{ error }}" not in source


def test_creation_page_exposes_history_drawer_for_replaying_workflow_trace() -> None:
    source = read_source("pages/CreationPage.vue")
    workflows = read_source("services/workflows.js")
    top_actions_block = source.split('<div class="top-actions">', 1)[1].split("</div>", 1)[0]
    history_drawer_block = source.split('class="side-drawer history-drawer"', 1)[1].split(
        "</aside>", 1
    )[0]
    history_list_rule = source.split(".history-list button {", 1)[1].split("}", 1)[0]

    assert "History" in source
    assert 'title="历史创作"' in top_actions_block
    assert '@click="openHistoryDrawer"' in top_actions_block
    assert top_actions_block.index('title="历史创作"') < top_actions_block.index(
        '@click="runThread"'
    )
    assert "historyDrawerOpen" in source
    assert "historyItems" in source
    assert "historyLoading" in source
    assert "listWorkflowHistory(workflowId" in source
    assert "getWorkflowRunResult(workflowId, item.thread_id" in source
    assert "function selectHistoryItem(item)" in source
    assert "threadId.value = item.thread_id;" in source
    assert "prompt.value = item.user_prompt;" in source
    assert "trace.value = selectedResult.trace;" in source
    assert "result.value = selectedResult.output;" in source
    assert "runResult.value = {" in source
    assert "focusNodeIdFromTrace(selectedResult.trace)" in source
    assert "hasArtifactValue(node.artifact_preview)" in source
    assert "history-list" in history_drawer_block
    assert "grid-template-columns: minmax(0, 1fr) 96px;" in history_list_rule
    assert "/api/workflows/${workflowId}/threads/history" in workflows
    assert "/api/workflows/${workflowId}/threads/${encodeURIComponent(threadId)}/trace" in workflows
    assert "/api/workflows/${workflowId}/threads/${encodeURIComponent(threadId)}/result" in workflows


def test_creation_page_restores_completed_history_result_inline() -> None:
    source = read_source("pages/CreationPage.vue")
    workflows = read_source("services/workflows.js")
    history_selection = source.split("async function selectHistoryItem(item)", 1)[1].split(
        "async function saveFinalDeliveryToAssets", 1
    )[0]

    assert "getWorkflowRunResult" in source
    assert "getWorkflowRunResult(workflowId, item.thread_id" in history_selection
    assert "result.value = selectedResult.output;" in history_selection
    assert "trace.value = selectedResult.trace;" in history_selection
    assert "runResult.value = {" in history_selection
    assert "...selectedResult" in history_selection
    assert "actions: []" in history_selection
    assert "resultDrawerOpen" not in history_selection
    assert "/api/workflows/${workflowId}/threads/${encodeURIComponent(threadId)}/result" in workflows


def test_creation_page_renders_completed_work_as_primary_content_without_duplicate_completion_ui() -> None:
    source = read_source("pages/CreationPage.vue")
    template = source.split("<template>", 1)[1].split("</template>", 1)[0]
    creator = template.split('v-if="pageMode === \'creator\'"', 1)[1].split(
        'v-else class="advanced-workspace"', 1
    )[0]

    assert 'v-if="finalDelivery" class="completed-work"' in creator
    completed_work = creator.split('v-if="finalDelivery" class="completed-work"', 1)[1].split(
        "</article>", 1
    )[0]
    for token in [
        "{{ finalDelivery.title }}",
        "{{ finalDelivery.style || \"暂无 Style Prompt\" }}",
        "{{ finalDelivery.lyrics || \"暂无歌词\" }}",
        '@click="saveFinalDeliveryToAssets"',
    ]:
        assert token in completed_work

    assert 'v-if="!finalDelivery" class="creator-progress"' in creator
    assert 'class="result-entry"' not in creator
    assert 'class="run-status-content completed"' not in creator
    assert 'class="run-status-dock"' not in creator


def test_creation_page_completed_work_removes_duplicate_actions_and_copies_delivery_fields() -> None:
    source = read_source("pages/CreationPage.vue")
    template = source.split("<template>", 1)[1].split("</template>", 1)[0]
    creator = template.split('v-if="pageMode === \'creator\'"', 1)[1].split(
        'v-else class="advanced-workspace"', 1
    )[0]
    completed_work = creator.split('v-if="finalDelivery" class="completed-work"', 1)[1].split(
        "</article>", 1
    )[0]

    assert '<header v-if="!finalDelivery" class="creator-header">' in creator
    assert '@click="startNewCreation"' not in completed_work
    assert completed_work.count('@click="copyDeliveryText(') == 2
    assert 'title="复制 Style Prompt"' in completed_work
    assert 'title="复制歌词"' in completed_work
    assert 'navigator.clipboard.writeText(text)' in source
    assert 'const copyMessage = ref("");' in source
    assert 'role="status"' in completed_work


def test_creation_page_history_replay_does_not_lock_global_api_target_as_live_waiting() -> None:
    source = read_source("pages/CreationPage.vue")
    live_waiting_rule = source.split("const hasLiveWaitingAction = computed(() => {", 1)[1].split(
        "});", 1
    )[0]
    busy_rule = source.split("const isWorkflowBusy = computed(() => {", 1)[1].split("});", 1)[0]

    assert "const hasLiveWaitingAction = computed(() => {" in source
    assert "Array.isArray(runResult.value?.waiting?.actions)" in live_waiting_rule
    assert "runResult.value.waiting.actions.length > 0" in live_waiting_rule
    assert "hasLiveWaitingAction.value" in busy_rule
    assert 'runResult.value?.status === "waiting"' not in busy_rule
    assert 'v-if="hasLiveWaitingAction && focusNode?.id === runResult.waiting.node_id"' in source


def test_auth_pages_include_yuetools_register_login_fields() -> None:
    login = read_source("pages/LoginPage.vue")
    register = read_source("pages/RegisterPage.vue")

    assert "登录乐兔工作室" in login
    assert "注册乐兔工作室" in register
    for old_brand in ["YTS Studio", "Creator OS"]:
        assert old_brand not in login
        assert old_brand not in register
    for text in ["账号", "密码", "登录"]:
        assert text in login
    assert "loginUser" in login
    assert "setSession" in login
    for text in ["邮箱", "密码", "确认密码", "同意", "注册"]:
        assert text in register
    assert "registerUser" in register
    assert "agreementAccepted" in register


def test_login_page_uses_music_studio_composition_instead_of_centered_auth_card() -> None:
    login = read_source("pages/LoginPage.vue")

    for token in [
        'class="login-stage"',
        'class="login-brand"',
        'class="record-visual"',
        'src="/favicon.svg"',
        'class="login-form-area"',
        'class="input-shell"',
        'class="password-toggle"',
        'const showPassword = ref(false);',
        ':type="showPassword ? \'text\' : \'password\'"',
        ':aria-label="showPassword ? \'隐藏密码\' : \'显示密码\'"',
    ]:
        assert token in login

    assert 'class="auth-panel"' not in login
    assert "grid-template-columns: minmax(0, 1.18fr) minmax(420px, 0.82fr);" in login
    assert "@media (max-width: 860px)" in login
    assert "grid-template-columns: minmax(0, 1fr);" in login
    assert "linear-gradient" not in login
    assert "border-radius: 999px" not in login


def test_register_page_matches_login_music_studio_composition() -> None:
    register = read_source("pages/RegisterPage.vue")

    for token in [
        'class="register-stage"',
        'class="register-brand"',
        'class="record-visual"',
        'src="/favicon.svg"',
        'class="register-form-area"',
        'class="input-shell"',
        'const showPassword = ref(false);',
        'const showConfirmPassword = ref(false);',
        ':type="showPassword ? \'text\' : \'password\'"',
        ':type="showConfirmPassword ? \'text\' : \'password\'"',
        'class="agreement-row"',
        'role="alert"',
    ]:
        assert token in register

    assert 'class="auth-panel"' not in register
    assert "grid-template-columns: minmax(0, 1.18fr) minmax(420px, 0.82fr);" in register
    assert "@media (max-width: 860px)" in register
    assert "grid-template-columns: minmax(0, 1fr);" in register
    assert "linear-gradient" not in register
    assert "border-radius: 999px" not in register

def test_profile_and_settings_pages_cover_user_and_credit_surfaces() -> None:
    profile = read_source("pages/ProfileSetupPage.vue")
    settings = read_source("pages/SettingsPage.vue")

    for text in ["头像", "昵称", "性别", "生日", "简介"]:
        assert text in profile
    assert "uploadAvatar" in profile
    assert "updateProfile" in profile

    for text in ["最近积分变动", "今日额度", "默认模型通道", "歌词生成", "图片生成", "音频特效"]:
        assert text in settings
    assert "fetchCreditLedger" in settings
    assert "fetchDailyUsage" in settings


def test_settings_page_exposes_logout_action_in_account_section() -> None:
    settings = read_source("pages/SettingsPage.vue")
    template = settings.split("<template>", 1)[1].split("</template>", 1)[0]
    account_section = template.split("<section v-else", 1)[1]

    assert "退出登录" in settings
    assert "LogOut" in settings
    assert "useAuthStore" in settings
    assert "auth.logoutAction()" in settings
    assert 'router.push({ name: "login" })' in settings
    assert 'class="danger-zone"' in account_section
    assert 'class="logout-button"' in account_section


def test_assets_page_exposes_song_inspiration_gallery_and_audio_tabs() -> None:
    assets = read_source("pages/AssetsPage.vue")

    for text in ["歌曲灵感", "图片大全", "音频特效"]:
        assert text in assets
    for field in ["原始 prompt", "歌名", "Style Prompt", "Lyric", "时间"]:
        assert field in assets
    assert "Suno Style Prompt" not in assets
    assert "listSongs" in assets
    assert "saveSong" in read_source("services/songs.js")


def test_assets_page_defaults_to_list_with_detail_drawer_layout() -> None:
    assets = read_source("pages/AssetsPage.vue")

    for class_name in [
        "asset-toolbar",
        "asset-workbench",
        "asset-library",
        "library-head",
        "asset-list",
        "asset-list-head",
        "asset-row",
        "asset-drawer-layer",
        "asset-detail-drawer",
        "detail-section",
        "preview-block",
        "lyric-text",
        "asset-empty",
    ]:
        assert class_name in assets
    assert 'const activeTab = ref("songs");' in assets
    assert "visibleAssets" in assets
    assert "selectedAsset" in assets
    assert "selectAsset" in assets
    assert '@click.stop="selectAsset(item)"' in assets
    assert '@click="handlePageClick"' in assets
    assert "function handlePageClick(event)" in assets
    assert 'target.closest(".asset-row")' in assets
    assert '<Teleport to="body">' in assets
    assert 'aria-modal="false"' in assets
    assert 'role="dialog"' in assets
    assert "drawer-backdrop" not in assets
    assert ".asset-workbench.has-selection" not in assets
    assert "grid-template-columns: var(--asset-list-columns);" in assets
    assert "formatAssetTime" in assets
    assert "asset-composer" not in assets
    assert "composer-form" not in assets
    assert "新增灵感" not in assets
    assert "saveSong" not in assets
    assert "song-card-grid" not in assets
    assert "building-panel" not in assets


def test_assets_page_uses_concise_heading_and_aligned_list_columns() -> None:
    assets = read_source("pages/AssetsPage.vue")
    page_header_block = assets.split('<header class="page-header">', 1)[1].split("</header>", 1)[0]
    library_head_block = assets.split('<div class="library-head">', 1)[1].split("</div>", 2)[0]
    asset_list_head_rule = assets.split(".asset-list-head,\n.asset-row {", 1)[1].split("}", 1)[0]
    asset_list_head_rule_only = assets.split(".asset-list-head {", 1)[1].split("}", 1)[0]
    asset_row_rule = assets.rsplit(".asset-row {", 1)[1].split("}", 1)[0]
    asset_time_rule = assets.rsplit(".asset-row time {", 1)[1].split("}", 1)[0]

    assert "<p>资产</p>" not in page_header_block
    assert page_header_block.count("<h1>资产</h1>") == 1
    assert "资产库" not in library_head_block
    assert "--asset-list-columns: minmax(180px, 0.78fr) minmax(280px, 1.42fr) 118px;" in assets
    assert "grid-template-columns: var(--asset-list-columns);" in asset_list_head_rule
    assert "justify-items: start;" in asset_list_head_rule_only
    assert ".asset-list-head span:last-child" in assets
    assert "justify-self: end;" in assets
    assert "position: relative;" in asset_row_rule
    assert "border-radius: 0;" in asset_row_rule
    assert "font-variant-numeric: tabular-nums;" in asset_time_rule


def test_assets_page_uses_deep_sea_night_watch_visual_system() -> None:
    assets = read_source("pages/AssetsPage.vue")
    page_rule = assets.split(".page {", 1)[1].split("}", 1)[0]
    asset_library_rule = assets.split(".asset-library {", 1)[1].split("}", 1)[0]
    selected_row_rule = assets.split(
        ".asset-row:hover,\n.asset-row:focus-visible,\n.asset-row.selected {", 1
    )[1].split("}", 1)[0]
    detail_section_rule = assets.split(".detail-section {", 1)[1].split("}", 1)[0]
    asset_detail_drawer_rule = assets.split(".asset-detail-drawer {", 1)[1].split("}", 1)[0]

    assert "linear-gradient(110deg, rgba(34, 211, 238, 0.07), transparent 34%)" in page_rule
    assert "background: transparent;" in asset_library_rule
    assert "box-shadow: none;" in asset_library_rule
    assert (
        "background: linear-gradient(90deg, rgba(14, 165, 233, 0.18), rgba(20, 184, 166, 0.08) 58%, transparent);"
        in selected_row_rule
    )
    assert "border: 0;" in detail_section_rule
    assert "box-shadow: inset 0 1px 0 rgba(125, 211, 252, 0.1);" in detail_section_rule
    assert "border-left: 0;" in asset_detail_drawer_rule
    assert "inset 1px 0 0 rgba(125, 211, 252, 0.08)" in asset_detail_drawer_rule


def test_assets_page_uses_same_list_detail_pattern_for_image_and_audio_assets() -> None:
    assets = read_source("pages/AssetsPage.vue")

    for token in [
        "imageAssetRows",
        "audioAssetRows",
        "assetTypeMeta",
        "activeTabMeta",
        "assetTitleLabel",
        "assetPrimaryLabel",
        "assetSecondaryLabel",
    ]:
        assert token in assets
    for text in ["图片标题", "图片 prompt", "音频标题", "音频 prompt"]:
        assert text in assets
    assert "activeTabMeta.emptyTitle" in assets
    assert "selectedAsset.primaryText" in assets
    assert "selectedAsset.secondaryText" in assets


def test_assets_page_supports_copying_generated_song_fields_without_framed_tabs() -> None:
    assets = read_source("pages/AssetsPage.vue")
    asset_tabs_rule = assets.split(".asset-tabs {", 1)[1].split("}", 1)[0]
    asset_tab_button_rule = assets.split(".asset-tabs button {", 1)[1].split("}", 1)[0]
    asset_tab_hover_rule = assets.split(
        ".asset-tabs button:hover,\n.asset-tabs button:focus-visible {", 1
    )[1].split("}", 1)[0]
    asset_tab_active_hover_rule = assets.split(
        ".asset-tabs button.active:hover,\n.asset-tabs button.active:focus-visible {", 1
    )[1].split("}", 1)[0]
    asset_library_rule = assets.split(".asset-library {", 1)[1].split("}", 1)[0]
    asset_drawer_layer_rule = assets.split(".asset-drawer-layer {", 1)[1].split("}", 1)[0]
    asset_detail_drawer_rule = assets.split(".asset-detail-drawer {", 1)[1].split("}", 1)[0]
    lyric_text_rule = assets.split(".lyric-text {", 1)[1].split("}", 1)[0]

    for text in [
        "copyAssetText",
        "navigator.clipboard.writeText",
        "已复制${label}",
        "copy-title",
        "copy-field",
        "\\n\\n$1\\n",
    ]:
        assert text in assets
    for label in ["歌名", "Style Prompt", "歌词"]:
        assert f"copyAssetText('{label}'" in assets
    assert "border:" not in asset_tabs_rule
    assert "cursor: pointer;" in asset_tab_button_rule
    assert "background: rgba(34, 211, 238, 0.11);" in asset_tab_hover_rule
    assert "box-shadow: 0 10px 24px rgba(2, 8, 20, 0.18);" in asset_tab_hover_rule
    assert "transform: translateY(-1px);" in asset_tab_hover_rule
    assert "outline: 2px solid rgba(14, 165, 233, 0.42);" in asset_tab_hover_rule
    assert "background: rgba(14, 165, 233, 0.24);" in asset_tab_active_hover_rule
    assert "border:" not in asset_library_rule
    assert "position: fixed;" in asset_drawer_layer_rule
    assert "inset: 0;" in asset_drawer_layer_rule
    assert "pointer-events: none;" in asset_drawer_layer_rule
    assert "position: absolute;" in asset_detail_drawer_rule
    assert "right: 0;" in asset_detail_drawer_rule
    assert "top: 0;" in asset_detail_drawer_rule
    assert "bottom: 0;" in asset_detail_drawer_rule
    assert "height: 100vh;" in asset_detail_drawer_rule
    assert "border-radius: 0;" in asset_detail_drawer_rule
    assert "color-scheme: dark;" in asset_detail_drawer_rule
    assert (
        "background: linear-gradient(180deg, #163955 0%, #0b2135 100%);" in asset_detail_drawer_rule
    )
    assert "#f8fbff" not in assets
    assert "#edf6fc" not in assets
    assert "white-space: pre-wrap;" in lyric_text_rule
    assert "word-break: break-word;" in lyric_text_rule


def test_creation_page_can_save_final_delivery_to_song_assets() -> None:
    creation = read_source("pages/CreationPage.vue")

    assert "saveFinalDeliveryToAssets" in creation
    assert "saveSong" in creation
    assert "保存到资产" in creation
    assert "finalDelivery.title" in creation
    assert "finalDelivery.style" in creation
    assert "finalDelivery.lyrics" in creation


def test_music_page_is_the_default_player_surface() -> None:
    music = read_source("pages/MusicPage.vue")

    for text in ["播放队列", "导入", "暂无歌曲"]:
        assert text in music
    assert '<header class="music-topbar">' not in music
    assert '<div class="title-stack">' not in music
    assert "<h1>音乐播放器</h1>" not in music
    assert "usePlayerStore" in music
    assert "usePlaylistStore" in music


def test_music_page_prioritizes_minimal_wave_player_without_lyrics() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")

    for token in [
        "music-studio",
        "minimal-player",
        "player-stage",
        "YtsAudioPlayer",
        "loopModes",
        "cycleLoopMode",
        "循环播放",
        "单曲循环",
        "随机播放",
    ]:
        assert token in music
    for token in [
        "media-controller",
        "media-control-bar",
        "播放模式",
    ]:
        assert token in player
    for removed_rendering_surface in ["hero-wave", "waveformRef", "WaveSurfer.create"]:
        assert removed_rendering_surface not in player
    for removed_surface in [
        "session-panel",
        "stream-card",
        "mix-card",
        "time-ruler",
        "播放参数",
        "查看播放队列",
        "查看播放历史",
    ]:
        assert removed_surface not in music
    assert "歌词" not in music
    assert "lyric" not in music.lower()


def test_music_page_player_surface_has_no_panel_frame_or_wavesurfer_rendering() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")
    player_rule = music.split(".minimal-player {", 1)[1].split("}", 1)[0]

    assert "background: transparent;" in player_rule
    assert "border: 0;" in player_rule
    assert "border-radius: 0;" in player_rule
    assert "box-shadow: none;" in player_rule
    assert "player-spacer" not in player
    assert "hero-wave" not in player
    assert "waveform-canvas" not in player
    assert "WaveSurfer" not in player
    assert "cursorColor" not in player
    assert "cursorWidth" not in player


def test_music_page_uses_right_drawer_for_queue_and_history() -> None:
    music = read_source("pages/MusicPage.vue")
    template = music.split("<template>", 1)[1].split("</template>", 1)[0]
    drawer_layer_block = template.split('<div v-if="playlistDrawerOpen" class="drawer-layer"', 1)[
        1
    ].split("</aside>", 1)[0]
    drawer_header_block = drawer_layer_block.split('<header class="drawer-header"', 1)[1].split(
        "</header>", 1
    )[0]
    drawer_layer_rule = music.split(".drawer-layer {", 1)[1].split("}", 1)[0]
    drawer_scrim_rule = music.split(".drawer-scrim {", 1)[1].split("}", 1)[0]
    drawer_header_rule = music.split(".drawer-header {", 1)[1].split("}", 1)[0]
    drawer_title_rule = music.split(".drawer-title {", 1)[1].split("}", 1)[0]
    drawer_title_icon_rule = music.split(".drawer-title > span {", 1)[1].split("}", 1)[0]

    for token in [
        "playlistDrawerOpen",
        "playlistDrawerOpen = ref(false)",
        "drawerMode",
        "drawer-layer",
        "drawer-scrim",
        "drawer-panel",
        "drawer-title",
        "drawer-tab",
        "drawerTracks",
        "playHistory",
        "recordHistory",
        "showDrawer",
        "播放历史",
        "删除历史",
        "播放列表",
    ]:
        assert token in music
    assert 'aria-label="关闭播放列表面板"' in drawer_layer_block
    assert '@click="playlistDrawerOpen = false"' in drawer_layer_block
    assert '<ListMusic :size="18" />' in drawer_header_block
    assert '<button class="drawer-collapse"' in drawer_header_block
    assert drawer_header_block.index('class="drawer-title"') < drawer_header_block.index(
        'class="drawer-collapse"'
    )
    assert "position: fixed;" in drawer_layer_rule
    assert "inset: 0;" in drawer_layer_rule
    assert "pointer-events: none;" in drawer_layer_rule
    assert "position: absolute;" in drawer_scrim_rule
    assert "pointer-events: auto;" in drawer_scrim_rule
    assert "display: flex;" in drawer_header_rule
    assert "justify-content: space-between;" in drawer_header_rule
    assert "grid-template-columns: 42px minmax(0, 1fr);" in drawer_title_rule
    assert "background: rgba(14, 165, 233, 0.22);" in drawer_title_icon_rule
    assert 'class="drawer-backdrop"' not in music
    assert "right: 0;" in music
    assert "transform: translateX(0);" in music


def test_music_playlist_drawer_supports_delete_history_and_restore_actions() -> None:
    music = read_source("pages/MusicPage.vue")
    template = music.split("<template>", 1)[1].split("</template>", 1)[0]
    drawer_block = template.split('<aside class="drawer-panel open"', 1)[1].split("</aside>", 1)[0]

    for token in [
        "deletedTracks",
        'drawerMode === "deleted"',
        "handleDeletePlaylistItem",
        "handleRestorePlaylistItem",
        "await playlist.deleteItem(track.id)",
        "await playlist.restoreItem(track.id)",
        "删除历史",
        "移除",
        "恢复",
        "暂无删除历史",
    ]:
        assert token in music
    assert '<Trash2 :size="16" /> 删除历史' in drawer_block
    assert 'class="drawer-row-main"' in drawer_block
    assert 'class="drawer-row-action danger"' in drawer_block
    assert 'class="drawer-row-action restore"' in drawer_block
    assert '@click.stop="handleDeletePlaylistItem(track)"' in drawer_block
    assert '@click.stop="handleRestorePlaylistItem(track)"' in drawer_block


def test_music_playlist_drawer_uses_compact_single_line_rows() -> None:
    music = read_source("pages/MusicPage.vue")
    drawer_list_rule = music.split(".drawer-list {", 1)[1].split("}", 1)[0]
    drawer_tab_rule = music.split(".drawer-tab {", 1)[1].split("}", 1)[0]
    drawer_row_rule = music.split(".drawer-row {", 1)[1].split("}", 1)[0]
    drawer_row_active_rule = music.split(".drawer-row:hover,", 1)[1].split("}", 1)[0]
    drawer_index_rule = music.split(".drawer-row span {", 1)[1].split("}", 1)[0]
    drawer_title_rule = music.split(".drawer-row strong {", 1)[1].split("}", 1)[0]
    drawer_meta_rule = music.split(".drawer-row small {", 1)[1].split("}", 1)[0]

    assert "align-content: start;" in drawer_list_rule
    assert "gap: 4px;" in drawer_list_rule
    assert "grid-auto-rows: max-content;" in drawer_list_rule
    assert "min-height: 38px;" in drawer_tab_rule
    assert "border: 1px solid rgba(125, 211, 252, 0.12);" in drawer_tab_rule
    assert "box-sizing: border-box;" in drawer_row_rule
    assert "border: 0;" in drawer_row_rule
    assert "border-radius: 6px;" in drawer_row_rule
    assert "grid-template-columns: 24px minmax(0, 1fr) minmax(48px, 78px);" in drawer_row_rule
    assert "align-items: center;" in drawer_row_rule
    assert "min-height: 34px;" in drawer_row_rule
    assert "padding: 5px 8px;" in drawer_row_rule
    assert "width: 100%;" in drawer_row_rule
    assert "box-shadow: inset 2px 0 0 rgba(34, 211, 238, 0.42);" in drawer_row_active_rule
    assert "grid-row: span 2;" not in drawer_index_rule
    assert "font-size: 11px;" in drawer_index_rule
    assert "line-height: 1;" in drawer_index_rule
    assert "font-size: 12px;" in drawer_title_rule
    assert "font-size: 13px;" not in drawer_title_rule
    assert "line-height: 1.1;" in drawer_title_rule
    assert "font-size: 11px;" in drawer_meta_rule
    assert "justify-self: end;" in drawer_meta_rule
    assert "line-height: 1;" in drawer_meta_rule


def test_music_page_uses_edge_progress_and_vertical_side_actions_without_large_frames() -> None:
    music = read_source("pages/MusicPage.vue")
    side_actions_block = music.split('<div class="side-actions"', 1)[1].split("</div>", 1)[0]
    side_actions_rule = music.split(".side-actions {", 1)[1].split("}", 1)[0]
    minimal_player_rule = music.split(".minimal-player {", 1)[1].split("}", 1)[0]
    player = read_source("components/YtsAudioPlayer.vue")
    media_shell_rule = player.split(".media-shell {", 1)[1].split("}", 1)[0]

    assert 'class="side-actions"' in music
    assert 'title="播放队列"' in side_actions_block
    assert "@click=\"showDrawer('queue')\"" in side_actions_block
    assert '<ListMusic :size="17" />' in side_actions_block
    assert 'class="drawer-peek"' not in music
    assert "ChevronLeft" not in music
    assert "flex-direction: column;" in side_actions_rule
    assert "right: 14px;" in side_actions_rule
    assert "top: 50%;" in side_actions_rule
    assert "border: 0;" in minimal_player_rule
    assert "border: 0;" in media_shell_rule
    assert "box-shadow: none;" in media_shell_rule


def test_auth_credentials_are_not_persisted_in_web_storage() -> None:
    combined = (
        read_source("stores/auth.js")
        + read_source("services/transport.js")
        + read_source("router/index.js")
    )

    assert "yts-access-token" not in combined
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined
