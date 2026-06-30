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


def test_app_shell_router_and_default_music_route_are_defined() -> None:
    app = read_source("App.vue")
    router = read_source("router/index.js")
    main = read_source("main.js")
    shell = read_source("app/AppShell.vue")

    assert "<RouterView />" in app
    assert 'path: "/"' in router
    assert 'redirect: "/music"' in router
    for route in ["/music", "/studio", "/assets", "/settings", "/profile/setup", "/auth/login", "/auth/register"]:
        assert route in router
    assert "createPinia()" in main
    assert ".use(router)" in main
    for label in ["音乐", "创作", "资产", "设置"]:
        assert label in shell


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
    http = read_source("services/http.js")

    assert 'response.status === 401' in http
    assert 'localStorage.removeItem("yts-access-token")' in http
    assert 'localStorage.removeItem("yts-user")' in http
    assert 'window.dispatchEvent(new CustomEvent("yts-auth-expired"' in http


def test_app_shell_redirects_to_login_when_auth_expires() -> None:
    shell = read_source("app/AppShell.vue")

    assert 'window.addEventListener("yts-auth-expired", handleAuthExpired)' in shell
    assert 'window.removeEventListener("yts-auth-expired", handleAuthExpired)' in shell
    assert 'router.push({ name: "login", query: { redirect: route.fullPath } })' in shell


def test_auth_store_only_absorbs_unauthorized_hydration_errors() -> None:
    auth = read_source("stores/auth.js")

    assert "if (err?.status === 401)" in auth
    assert "this.clearSession();" in auth
    assert "throw err;" in auth


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
        "var(--color-accent)",
    ]:
        assert token in shell


def test_app_shell_settings_navigation_lives_at_sidebar_bottom_without_credit_card() -> None:
    shell = read_source("app/AppShell.vue")
    sidebar_rule = shell.split(".creator-sidebar {", 1)[1].split("}", 1)[0]
    bottom_nav_rule = shell.split(".creator-bottom-nav {", 1)[1].split("}", 1)[0]

    assert "const primaryNavItems = [" in shell
    assert 'key: "settings"' not in shell.split("const primaryNavItems = [", 1)[1].split("];", 1)[0]
    assert 'const settingsNavItem = { key: "settings", label: "设置", to: "/settings", icon: Settings2 };' in shell
    assert 'class="creator-bottom-nav"' in shell
    assert "display: flex;" in sidebar_rule
    assert "flex-direction: column;" in sidebar_rule
    assert "margin-top: auto;" in bottom_nav_rule
    assert "display: grid;" not in bottom_nav_rule
    assert "creator-sidebar-card" not in shell
    assert "sidebar-card-label" not in shell
    assert "fetchCreditBalance" not in shell
    assert "fetchDailyUsage" not in shell
    assert "creditBalance" not in shell
    assert "dailyUsage" not in shell
    assert "歌词 {{" not in shell


def test_app_shell_active_navigation_has_no_outer_accent_border() -> None:
    shell = read_source("app/AppShell.vue")
    active_rule = shell.split(".creator-nav-item:hover,\n.creator-nav-item.active {", 1)[1].split("}", 1)[0]

    assert "border: 1px solid transparent;" in shell
    assert "border-color: var(--color-accent);" not in active_rule


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


def test_creation_page_uses_dark_theme_instead_of_broad_light_surfaces() -> None:
    source = read_source("pages/CreationPage.vue")

    for token in ["var(--color-bg)", "var(--color-panel)", "var(--color-text)", "var(--color-accent)"]:
        assert token in source
    for color in BROAD_LIGHT_SURFACES:
        assert color not in source


def test_creation_page_uses_deep_sea_studio_branding() -> None:
    source = read_source("pages/CreationPage.vue")

    assert "深海工作室" in source
    assert "制作流程" in source
    assert "YTS Studio" not in source


def test_auth_pages_include_yuetools_register_login_fields() -> None:
    login = read_source("pages/LoginPage.vue")
    register = read_source("pages/RegisterPage.vue")

    assert "登录深海工作室" in login
    assert "注册深海工作室" in register
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


def test_profile_and_settings_pages_cover_user_and_credit_surfaces() -> None:
    profile = read_source("pages/ProfileSetupPage.vue")
    settings = read_source("pages/SettingsPage.vue")

    for text in ["头像", "昵称", "性别", "生日", "简介"]:
        assert text in profile
    assert "uploadAvatar" in profile
    assert "updateProfile" in profile

    for text in ["积分流水", "每日额度", "模型偏好", "歌词生成", "图片生成", "音频特效"]:
        assert text in settings
    assert "fetchCreditLedger" in settings
    assert "fetchDailyUsage" in settings


def test_settings_page_exposes_logout_action_in_header() -> None:
    settings = read_source("pages/SettingsPage.vue")

    assert "退出登录" in settings
    assert "LogOut" in settings
    assert "useAuthStore" in settings
    assert "auth.logoutAction()" in settings
    assert 'router.push({ name: "login" })' in settings
    assert "settings-actions" in settings
    assert "logout-button" in settings


def test_assets_page_exposes_song_inspiration_gallery_and_audio_tabs() -> None:
    assets = read_source("pages/AssetsPage.vue")

    for text in ["歌曲灵感", "图片大全", "音频特效", "待建设"]:
        assert text in assets
    for field in ["原始 Prompt", "歌名", "Suno Style Prompt", "Lyric"]:
        assert field in assets
    assert "listSongs" in assets
    assert "saveSong" in read_source("services/songs.js")


def test_assets_page_uses_compact_workbench_layout() -> None:
    assets = read_source("pages/AssetsPage.vue")

    for class_name in [
        "asset-toolbar",
        "asset-workbench",
        "asset-library",
        "library-head",
        "song-card-grid",
        "preview-block",
        "lyric-text",
        "asset-empty",
    ]:
        assert class_name in assets
    assert "grid-template-columns: minmax(0, 1fr);" in assets
    assert "grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));" in assets
    assert "asset-composer" not in assets
    assert "composer-form" not in assets
    assert "新增灵感" not in assets
    assert "saveSong" not in assets
    assert "asset-grid" not in assets
    assert "song-list" not in assets


def test_assets_page_supports_copying_generated_song_fields_without_framed_tabs() -> None:
    assets = read_source("pages/AssetsPage.vue")
    asset_tabs_rule = assets.split(".asset-tabs {", 1)[1].split("}", 1)[0]
    asset_tab_button_rule = assets.split(".asset-tabs button {", 1)[1].split("}", 1)[0]
    asset_tab_hover_rule = assets.split(".asset-tabs button:hover,\n.asset-tabs button:focus-visible {", 1)[1].split("}", 1)[0]
    asset_tab_active_hover_rule = assets.split(
        ".asset-tabs button.active:hover,\n.asset-tabs button.active:focus-visible {", 1
    )[1].split("}", 1)[0]
    asset_library_rule = assets.split(".asset-library {", 1)[1].split("}", 1)[0]
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
    for label in ["歌名", "Suno Style Prompt", "歌词"]:
        assert f"copyAssetText('{label}'" in assets
    assert "border:" not in asset_tabs_rule
    assert "cursor: pointer;" in asset_tab_button_rule
    assert "background: rgba(14, 165, 233, 0.1);" in asset_tab_hover_rule
    assert "box-shadow: inset 0 0 0 1px rgba(14, 165, 233, 0.2);" in asset_tab_hover_rule
    assert "transform: translateY(-1px);" in asset_tab_hover_rule
    assert "outline: 2px solid rgba(14, 165, 233, 0.42);" in asset_tab_hover_rule
    assert "background: rgba(14, 165, 233, 0.18);" in asset_tab_active_hover_rule
    assert "border:" not in asset_library_rule
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

    for text in ["音乐播放器", "播放队列", "导入", "暂无歌曲"]:
        assert text in music
    assert "usePlayerStore" in music
    assert "usePlaylistStore" in music
