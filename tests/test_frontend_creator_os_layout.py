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
    http = read_source("services/transport.js")

    assert "status === 401" in http
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
    assert 'aria-label="深海工作室"' in favicon
    assert "brand-spark-large" in favicon
    assert "brand-spark-small" in favicon
    assert "<title>深海工作室</title>" in index


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
    assert "display: grid;" in bottom_nav_rule
    assert "creator-sidebar-card" not in shell
    assert "sidebar-card-label" not in shell
    assert "fetchCreditBalance" not in shell
    assert "fetchDailyUsage" not in shell
    assert "creditBalance" not in shell
    assert "dailyUsage" not in shell
    assert "歌词 {{" not in shell


def test_app_shell_api_target_switch_lives_above_settings_navigation() -> None:
    shell = read_source("app/AppShell.vue")
    bottom_nav_block = shell.split('<nav class="creator-bottom-nav"', 1)[1].split("</nav>", 1)[0]

    assert 'import { useEnvironmentStore } from "../stores/environment";' in shell
    assert "const environment = useEnvironmentStore();" in shell
    assert "environment.options" in shell
    assert "environment.target" in shell
    assert "environment.setTarget(item.value)" in shell
    assert "environment.checkAllHealth()" in shell
    assert "environment.targetHealth(item.value)" in shell
    assert 'class="global-target-switch"' in bottom_nav_block
    assert 'aria-label="API 环境"' in bottom_nav_block
    assert 'v-for="item in environment.options"' in bottom_nav_block
    assert ':disabled="environment.switchLocked"' in bottom_nav_block
    assert "target-status-dot" in bottom_nav_block
    assert 'class="target-lock-note"' in bottom_nav_block
    assert bottom_nav_block.index('class="global-target-switch"') < bottom_nav_block.index(
        ":to=\"settingsNavItem.to\""
    )


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
    assert 'import { openBinaryStream } from "../services/transport";' in stream_player
    assert "openBinaryStream(\"\", {" in stream_player
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
        'requestBlob(`/api/music/file/${contentHash}`',
        "listPlaylists",
        "requestJson(`/api/music/playlists",
        "ensureDefaultPlaylist",
        'requestJson("/api/music/playlists/default"',
        "appendPlaylistItems",
        "requestJson(`/api/music/playlists/${playlistId}/items`",
        "reorderPlaylistItems",
        "requestJson(`/api/music/playlists/${playlistId}/items/reorder`",
    ]:
        assert token in service

    for token in [
        "playlists: []",
        "currentPlaylistId",
        "playlistItems",
        "ensureDefault",
        "loadItems",
        "appendItems",
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
    timeline_block = template.split('<div class="timeline-row"', 1)[1].split("</div>", 1)[0]

    assert "currentTimeLabel" in player
    assert "durationLabel" in player
    assert 'class="time-progress"' in template
    assert "时间进度：{{ currentTimeLabel }}/{{ durationLabel }}" in template
    assert "<media-time-range></media-time-range>" in timeline_block
    assert "<media-time-display" not in timeline_block
    assert "<media-duration-display" not in timeline_block
    assert "grid-template-rows: auto auto auto;" in player
    assert "grid-template-columns: minmax(0, 1fr);" in player


def test_audio_player_animates_waveform_while_playing() -> None:
    player = read_source("components/YtsAudioPlayer.vue")

    assert ':class="{ empty: !sourceUrl, playing }"' in player
    assert ".yts-audio-player.playing .hero-wave::after" in player
    assert ".yts-audio-player.playing .waveform-canvas" in player
    assert "@keyframes waveform-shimmer" in player
    assert "@keyframes waveform-breathe" in player
    assert "@media (prefers-reduced-motion: reduce)" in player


def test_audio_player_formats_media_errors_without_object_string() -> None:
    player = read_source("components/YtsAudioPlayer.vue")

    assert "function formatPlaybackError(err)" in player
    assert "MEDIA_ERROR_MESSAGES" in player
    assert "音频加载失败" in player
    assert 'String(err)' not in player.split('wave.value.on("error"', 1)[1].split("});", 1)[0]


def test_music_player_places_track_identity_inside_open_source_player_shell() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")
    assert 'class="control-row"' in player
    control_row_block = player.split('<div class="control-row"', 1)[1].split("</media-control-bar>", 1)[0]

    assert 'class="player-meta"' not in music
    assert 'class="transport-bar"' not in music
    assert 'class="track-summary"' in player
    assert ':track="currentTrack"' in music
    assert 'trackTitle' in player
    assert 'trackArtist' in player
    assert player.index('class="timeline-row"') < player.index('class="control-row"')
    assert 'class="track-summary"' in control_row_block
    assert control_row_block.index('class="track-summary"') < control_row_block.index('class="button-groups"')


def test_music_player_uses_open_source_media_components_instead_of_hand_rolled_controls() -> None:
    package_json = read_frontend_file("package.json")
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")

    assert '"media-chrome"' in package_json
    assert '"wavesurfer.js"' in package_json
    assert 'import "media-chrome";' in player
    assert 'import WaveSurfer from "wavesurfer.js";' in player
    for custom_element in [
        "<media-controller",
        "<media-play-button",
        "<media-time-range",
        "<media-mute-button",
        "<media-volume-range",
    ]:
        assert custom_element in player
    assert 'class="time-progress"' in player
    assert "<media-time-display" not in player.split("<template>", 1)[1].split("</template>", 1)[0]
    assert "<media-duration-display" not in player.split("<template>", 1)[1].split("</template>", 1)[0]
    assert 'ref="audioRef"' in player
    assert 'ref="waveformRef"' in player
    assert "WaveSurfer.create" in player
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
    assert 'class="timeline-row"' in player
    assert 'class="control-row"' in player
    assert 'class="button-groups"' in player
    timeline_row_block = player.split('<div class="timeline-row"', 1)[1].split("</div>", 1)[0]
    control_row_block = player.split('<div class="control-row"', 1)[1].split("</media-control-bar>", 1)[0]
    control_row_rule = player.split(".control-row {", 1)[1].split("}", 1)[0]
    button_groups_rule = player.split(".button-groups {", 1)[1].split("}", 1)[0]
    track_rule = player.split(".track-summary {", 1)[1].split("}", 1)[0]
    artist_rule = player.split(".track-summary small {", 1)[1].split("}", 1)[0]

    for class_name in ["timeline-row", "control-row", "track-summary", "button-groups", "transport-group", "utility-group"]:
        assert class_name in player
    assert player.index('class="time-progress"') < player.index('class="timeline-row"')
    assert player.index('class="timeline-row"') < player.index('class="control-row"')
    assert "<media-time-range" in timeline_row_block
    assert "<media-time-display" not in timeline_row_block
    assert "<media-duration-display" not in timeline_row_block
    assert "transport-group" not in timeline_row_block
    assert "utility-group" not in timeline_row_block
    assert 'class="track-summary"' in control_row_block
    assert 'class="button-groups"' in control_row_block
    assert control_row_block.index('class="track-summary"') < control_row_block.index('class="button-groups"')
    assert 'class="transport-group"' in control_row_block
    assert 'class="utility-group"' in control_row_block
    assert "<ListMusic" not in player
    assert '"queue"' not in player
    assert '@queue="showDrawer' not in music
    assert "grid-template-rows: minmax(220px, 1fr) auto;" in root_rule
    assert "grid-template-rows: auto auto auto;" in controls_rule
    assert "max-width: none;" in controls_rule
    assert "margin-inline: auto;" in controls_rule
    assert "margin-inline: calc(0px - var(--stage-x-pad, 0px));" in timeline_rule
    assert "width: calc(100% + var(--stage-x-pad, 0px) + var(--stage-x-pad, 0px));" in timeline_rule
    assert "grid-template-columns: minmax(180px, 1fr) max-content;" in control_row_rule
    assert "justify-content: end;" in button_groups_rule
    assert "justify-items: start;" in track_rule
    assert "line-height: 1.2;" in track_rule
    assert "line-height: 1.2;" in artist_rule


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


def test_creation_page_shows_one_concise_user_facing_error_message() -> None:
    source = read_source("pages/CreationPage.vue")

    assert 'const displayError = computed(() => formatUserError(error.value));' in source
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
    history_drawer_block = source.split('class="side-drawer history-drawer"', 1)[1].split("</aside>", 1)[0]
    history_list_rule = source.split(".history-list button {", 1)[1].split("}", 1)[0]

    assert "History" in source
    assert 'title="历史创作"' in top_actions_block
    assert "@click=\"openHistoryDrawer\"" in top_actions_block
    assert top_actions_block.index('title="历史创作"') < top_actions_block.index("@click=\"runThread\"")
    assert "historyDrawerOpen" in source
    assert "historyItems" in source
    assert "historyLoading" in source
    assert "listWorkflowHistory(workflowId" in source
    assert "getWorkflowTrace(workflowId, item.thread_id" in source
    assert "function selectHistoryItem(item)" in source
    assert "threadId.value = item.thread_id;" in source
    assert "prompt.value = item.user_prompt;" in source
    assert "trace.value = selectedTrace;" in source
    assert "runResult.value = {" in source
    assert "waitingFromTrace(selectedTrace)" in source
    assert "focusNodeIdFromTrace(selectedTrace)" in source
    assert "hasArtifactValue(node.artifact_preview)" in source
    assert "history-list" in history_drawer_block
    assert "grid-template-columns: minmax(0, 1fr) 96px;" in history_list_rule
    assert "/api/workflows/${workflowId}/threads/history" in workflows
    assert "/api/workflows/${workflowId}/threads/${encodeURIComponent(threadId)}/trace" in workflows


def test_creation_page_history_replay_does_not_lock_global_api_target_as_live_waiting() -> None:
    source = read_source("pages/CreationPage.vue")
    live_waiting_rule = source.split("const hasLiveWaitingAction = computed(() => {", 1)[1].split("});", 1)[0]
    busy_rule = source.split("const isWorkflowBusy = computed(() => {", 1)[1].split("});", 1)[0]

    assert "const hasLiveWaitingAction = computed(() => {" in source
    assert "Array.isArray(runResult.value?.waiting?.actions)" in live_waiting_rule
    assert "runResult.value.waiting.actions.length > 0" in live_waiting_rule
    assert "hasLiveWaitingAction.value" in busy_rule
    assert "runResult.value?.status === \"waiting\"" not in busy_rule
    assert "v-if=\"hasLiveWaitingAction && focusNode?.id === runResult.waiting.node_id\"" in source


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
    assert "<Teleport to=\"body\">" in assets
    assert "aria-modal=\"false\"" in assets
    assert "role=\"dialog\"" in assets
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
    selected_row_rule = assets.split(".asset-row:hover,\n.asset-row:focus-visible,\n.asset-row.selected {", 1)[
        1
    ].split("}", 1)[0]
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
    asset_tab_hover_rule = assets.split(".asset-tabs button:hover,\n.asset-tabs button:focus-visible {", 1)[1].split("}", 1)[0]
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
    assert "background: linear-gradient(180deg, #163955 0%, #0b2135 100%);" in asset_detail_drawer_rule
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
        "hero-wave",
        "media-controller",
        "media-control-bar",
        "waveformRef",
        "播放模式",
    ]:
        assert token in player
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


def test_music_page_wave_surface_has_no_panel_frame_and_fades_into_background() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")
    player_rule = music.split(".minimal-player {", 1)[1].split("}", 1)[0]
    wave_rule = player.split(".hero-wave {", 1)[1].split("}", 1)[0]
    wave_glow_rule = player.split(".hero-wave::before {", 1)[1].split("}", 1)[0]

    assert "background: transparent;" in player_rule
    assert "border: 0;" in player_rule
    assert "border-radius: 0;" in player_rule
    assert "box-shadow: none;" in player_rule
    assert "background: transparent;" in wave_rule
    assert "border: 0;" in wave_rule
    assert "border-radius: 0;" in wave_rule
    assert "-webkit-mask-image:" in wave_rule
    assert "mask-image:" in wave_rule
    assert "radial-gradient(ellipse at center" in wave_glow_rule
    assert "repeating-linear-gradient" in wave_glow_rule
    assert 'cursorColor: "transparent"' in player
    assert "cursorWidth: 0" in player


def test_music_page_uses_right_drawer_for_queue_and_history() -> None:
    music = read_source("pages/MusicPage.vue")

    for token in [
        "playlistDrawerOpen",
        'playlistDrawerOpen = ref(false)',
        "drawerMode",
        "drawer-panel",
        "drawer-tab",
        "drawerTracks",
        "playHistory",
        "recordHistory",
        "showDrawer",
        "播放历史",
        "播放列表",
    ]:
        assert token in music
    assert 'class="drawer-backdrop"' not in music
    assert "right: 0;" in music
    assert "transform: translateX(0);" in music


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
    assert "<ListMusic :size=\"17\" />" in side_actions_block
    assert 'class="drawer-peek"' not in music
    assert "ChevronLeft" not in music
    assert "flex-direction: column;" in side_actions_rule
    assert "right: 14px;" in side_actions_rule
    assert "top: 50%;" in side_actions_rule
    assert "border: 0;" in minimal_player_rule
    assert "border: 0;" in media_shell_rule
    assert "box-shadow: none;" in media_shell_rule
