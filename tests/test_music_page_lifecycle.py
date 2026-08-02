from __future__ import annotations

from pathlib import Path

FRONTEND = Path("desktop/frontend/src")
FRONTEND_ROOT = Path("desktop/frontend")


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def read_frontend_file(relative_path: str) -> str:
    return (FRONTEND_ROOT / relative_path).read_text(encoding="utf-8")


def css_declarations(style: str, selector: str) -> dict[str, str]:
    rule = style.split(f"{selector} {{", 1)[1].split("}", 1)[0]
    declarations: dict[str, str] = {}
    for declaration in rule.split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        declarations[name.strip()] = " ".join(value.split())
    return declarations


def test_music_page_clears_player_queue_before_revoking_blob_urls_on_unmount() -> None:
    source = read_source("pages/MusicPage.vue")
    unmount_block = source.split("onBeforeUnmount(() => {", 1)[1].split("});", 1)[0]
    clear_urls_block = source.split("function clearPlayableTrackUrls() {", 1)[1].split(
        "}", 1
    )[0]

    assert "player.setQueue([]);" in unmount_block
    assert unmount_block.index("player.setQueue([]);") < unmount_block.index(
        "clearPlayableTrackUrls();"
    )
    assert "revokePlayableTrackUrls();" in clear_urls_block


def test_music_page_refreshes_after_environment_change_without_manual_refresh_button() -> None:
    music = read_source("pages/MusicPage.vue")
    target_watch_block = music.split("watch(\n  () => environment.target", 1)[1].split(
        "\n\nwatch(", 1
    )[0]

    assert "async (nextTarget, previousTarget) =>" in target_watch_block
    assert "if (nextTarget === previousTarget) return;" in target_watch_block
    assert "await refreshPlaylistWhenTargetReady(nextTarget);" in target_watch_block
    assert "RefreshCw" not in music
    assert 'title="刷新"' not in music
    assert 'aria-label="刷新"' not in music


def test_music_page_waits_for_target_health_before_loading_playlist() -> None:
    music = read_source("pages/MusicPage.vue")

    assert "async function refreshPlaylistWhenTargetReady(target = environment.target)" in music
    readiness_block = music.split(
        "async function refreshPlaylistWhenTargetReady(target = environment.target)", 1
    )[1].split("async function loadPlayableTrackUrls", 1)[0]
    assert "error.value = \"\";" in readiness_block
    assert "const healthStatus = await environment.checkHealth(target);" in readiness_block
    assert "if (target !== environment.target) return;" in readiness_block
    assert 'if (healthStatus !== "online") {' in readiness_block
    assert "environment.targetHealthDetail(target)" in readiness_block
    assert "await refreshPlaylist();" in readiness_block
    assert readiness_block.index("await environment.checkHealth(target)") < readiness_block.index(
        "await refreshPlaylist();"
    )


def test_playlist_splits_playback_critical_and_background_hydration() -> None:
    playlist_store = read_source("stores/playlist.js")
    minimal_block = playlist_store.split("async hydrateMinimal(", 1)[1].split(
        "async loadBackgroundMetadata(", 1
    )[0]
    background_block = playlist_store.split("async loadBackgroundMetadata(", 1)[1].split(
        "async hydrate(", 1
    )[0]

    assert "await this.loadPlaylists({ scope });" in minimal_block
    assert "await this.ensureDefault({ scope });" in minimal_block
    assert "await this.loadItems();" in minimal_block
    assert "loadDeletedItems" not in minimal_block
    assert "await this.loadDeletedItems({ playlistId });" in background_block
    assert "throw err;" in background_block


def test_music_startup_loads_background_metadata_after_current_track_url() -> None:
    music = read_source("pages/MusicPage.vue")
    refresh_block = music.split("async function refreshPlaylist()", 1)[1].split(
        "async function refreshPlaylistWhenTargetReady", 1
    )[0]

    assert "await playlist.hydrateMinimal({ scope: requestTarget });" in refresh_block
    assert "await loadCurrentTrackUrl({ target: requestTarget, requestVersion });" in refresh_block
    assert "void loadPlaylistBackgroundMetadata(requestTarget);" in refresh_block
    assert refresh_block.index("await loadCurrentTrackUrl") < refresh_block.index(
        "void loadPlaylistBackgroundMetadata"
    )

    target_watch_block = music.split("watch(\n  () => environment.target", 1)[1].split(
        "\n\nwatch(", 1
    )[0]
    assert "await refreshPlaylistWhenTargetReady(nextTarget);" in target_watch_block
    assert "await refreshPlaylist();" not in target_watch_block

    mounted_block = music.split("onMounted(async () => {", 1)[1].split("});", 1)[0]
    assert "await refreshPlaylistWhenTargetReady();" in mounted_block
    assert "await refreshPlaylist();" not in mounted_block


def test_music_page_loads_only_ready_renditions_and_refreshes_processing_state() -> None:
    music = read_source("pages/MusicPage.vue")
    playlist_store = read_source("stores/playlist.js")
    load_url = music.split("async function loadPlayableTrackUrl(", 1)[1].split(
        "function retainPlayableTrackUrls", 1
    )[0]
    unmount_block = music.split("onBeforeUnmount(() => {", 1)[1].split("});", 1)[0]

    assert 'const RENDITION_REFRESH_DELAY_MS = 1500;' in music
    assert 'if (item.playback_status !== "ready") return "";' in load_url
    assert "loadSongObjectUrl({ contentHash, target })" in load_url
    assert "function scheduleRenditionRefresh()" in music
    assert 'item.playback_status === "pending" || item.playback_status === "processing"' in music
    assert "setTimeout(async () =>" in music
    assert "clearTimeout(renditionRefreshTimer);" in unmount_block
    assert 'const VALID_PLAYBACK_STATUSES = new Set(["pending", "processing", "ready", "failed"]);' in playlist_store
    assert 'throw new Error("playlist item requires valid playback_status")' in playlist_store
    assert 'if (!item.rendition_profile) throw new Error("playlist item requires rendition_profile");' in playlist_store


def test_music_page_exposes_failed_rendition_diagnosis_and_explicit_retry() -> None:
    music = read_source("pages/MusicPage.vue")
    music_service = read_source("services/music.js")
    playlist_store = read_source("stores/playlist.js")
    import_drawer = read_source("components/MusicImportDrawer.vue")

    assert "export function retrySongRendition" in music_service
    assert "async retryRendition(contentHash)" in playlist_store
    assert "await retrySongRendition({ contentHash });" in playlist_store
    assert "function handleRetryRendition(track)" in music
    assert 'track.playbackStatus === "failed"' in music
    assert "track.playbackErrorMessage" in music
    assert '@click.stop="handleRetryRendition(track)"' in music
    assert 'item.playback_status === "failed"' in import_drawer
    assert "item.playback_error_message" in import_drawer
    assert "retryRendition(item)" in import_drawer


def test_music_page_persists_and_restores_last_playback_position() -> None:
    music = read_source("pages/MusicPage.vue")
    player_store = read_source("stores/player.js")
    player = read_source("components/YtsAudioPlayer.vue")
    refresh_block = music.split("async function refreshPlaylist()", 1)[1].split(
        "async function refreshPlaylistWhenTargetReady", 1
    )[0]
    time_update_block = music.split("function handleTimeUpdate(currentTime)", 1)[1].split(
        "function handleDurationChange", 1
    )[0]

    assert 'const PLAYBACK_RESUME_STORAGE_KEY = "yts-music-playback-state";' in music
    assert "const resumeSeekTime = ref(null);" in music
    assert "function readPlaybackResumeState()" in music
    assert "function writePlaybackResumeState(track, currentTime)" in music
    assert "function restorePlaybackResumeState()" in music
    assert "localStorage.getItem(PLAYBACK_RESUME_STORAGE_KEY)" in music
    assert "localStorage.setItem(" in music
    assert "target: environment.target" in music
    assert "trackId: track.id" in music
    assert "contentHash: track.contentHash" in music
    assert "currentTime: normalizedTime" in music
    assert "player.setQueue(tracks.value);" in refresh_block
    assert "restorePlaybackResumeState();" in refresh_block
    assert "await loadCurrentTrackUrl({ target: requestTarget, requestVersion });" in refresh_block
    assert refresh_block.index("player.setQueue(tracks.value);") < refresh_block.index(
        "restorePlaybackResumeState();"
    )
    assert refresh_block.index("restorePlaybackResumeState();") < refresh_block.index(
        "await loadCurrentTrackUrl({ target: requestTarget, requestVersion });"
    )
    assert "player.selectAt(resumeIndex, { currentTime: resumeState.currentTime, isPlaying: false });" in music
    assert "resumeSeekTime.value = resumeState.currentTime;" in music
    assert "writePlaybackResumeState(currentTrack.value, currentTime);" in time_update_block
    assert "selectAt(index, { currentTime = 0, isPlaying = false } = {})" in player_store
    assert "this.isPlaying = Boolean(isPlaying);" in player_store
    assert ':seek-time="resumeSeekTime"' in music
    assert '@seek-applied="handleSeekApplied"' in music
    assert 'seekTime: { type: Number, default: null }' in player
    assert '"seek-applied"' in player


def test_page_reload_restores_position_without_requesting_blocked_autoplay() -> None:
    music = read_source("pages/MusicPage.vue")
    read_block = music.split("function readPlaybackResumeState()", 1)[1].split(
        "function writePlaybackResumeState", 1
    )[0]
    write_block = music.split("function writePlaybackResumeState(track, currentTime)", 1)[1].split(
        "function restorePlaybackResumeState", 1
    )[0]
    restore_block = music.split("function restorePlaybackResumeState()", 1)[1].split(
        "async function startStreamPreview", 1
    )[0]

    assert "wasPlaying" not in read_block
    assert "wasPlaying" not in write_block
    assert "resumeState.wasPlaying" not in restore_block
    assert "isPlaying: false" in restore_block


def test_audio_player_applies_seek_time_after_source_load_before_playback_intent() -> None:
    player = read_source("components/YtsAudioPlayer.vue")
    source_watch_block = player.split("watch(sourceUrl, async (nextSourceUrl) => {", 1)[1].split(
        "watch(\n  () => props.playing", 1
    )[0]
    loaded_metadata_block = player.split("async function handleLoadedMetadata(event)", 1)[1].split(
        "function handleDurationChange", 1
    )[0]

    assert "function normalizedSeekTime()" in player
    assert "function applySeekTime()" in player
    assert "function sourceReadyForPlayback()" in player
    assert "if (!sourceReadyForPlayback()) return;" in player
    assert "requireAudio().currentTime = targetTime;" in player
    assert 'emit("seek-applied", targetTime);' in player
    assert "watch(\n  () => props.seekTime" in player
    assert "mediaReady.value = false;" in source_watch_block
    assert "const player = requireAudio();" in source_watch_block
    assert "player.src = nextSourceUrl;" in source_watch_block
    assert "player.load();" in source_watch_block
    assert "await syncPlaybackIntent();" not in source_watch_block
    assert "await applySeekTime();" not in source_watch_block
    assert "mediaReady.value = true;" in loaded_metadata_block
    assert "await applySeekTime();" in loaded_metadata_block
    assert "await syncPlaybackIntent();" in loaded_metadata_block
    assert loaded_metadata_block.index("await applySeekTime();") < loaded_metadata_block.index(
        "await syncPlaybackIntent();"
    )
    assert "WaveSurfer" not in player
    assert "waveformRef" not in player
    assert "requireWave" not in player
    assert "hero-wave" not in player


def test_audio_player_does_not_surface_autoplay_interruption_from_superseded_source_load() -> None:
    player = read_source("components/YtsAudioPlayer.vue")
    assert "watch(sourceUrl, async (nextSourceUrl) => {" in player
    source_watch_block = player.split("watch(sourceUrl, async (nextSourceUrl) => {", 1)[
        1
    ].split("watch(\n  () => props.playing", 1)[0]
    playback_intent_block = player.split("async function syncPlaybackIntent()", 1)[1].split(
        "function formatPlaybackError", 1
    )[0]
    pause_block = player.split("function handlePause()", 1)[1].split(
        "function handleEnded()", 1
    )[0]

    assert "const sourceLoadVersion = ref(0);" in player
    assert "const loadingSource = ref(false);" in player
    assert "function isPlayInterruptedBySourceLoad(err, playLoadVersion)" in player
    assert '"new load request"' in player
    assert "const playLoadVersion = sourceLoadVersion.value;" in playback_intent_block
    assert "if (isPlayInterruptedBySourceLoad(err, playLoadVersion)) return;" in playback_intent_block
    assert 'emit("play-error", formatPlaybackError(err));' in playback_intent_block
    assert "sourceLoadVersion.value += 1;" in source_watch_block
    assert "const loadVersion = sourceLoadVersion.value;" in source_watch_block
    assert "loadingSource.value = true;" in source_watch_block
    assert "if (loadVersion !== sourceLoadVersion.value) return;" in source_watch_block
    assert "player.src = nextSourceUrl;" in source_watch_block
    assert "player.src = sourceUrl.value;" not in source_watch_block
    assert "if (loadingSource.value && props.playing) return;" in pause_block


def test_queue_loop_repeats_the_current_track_when_the_queue_has_only_one_song() -> None:
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")
    ended_block = music.split("function handleAudioEnded()", 1)[1].split(
        "function handleTimeUpdate", 1
    )[0]

    assert 'repeatCurrent: { type: Boolean, default: false }' in player
    assert ':loop="repeatCurrent || loopMode === \'single\'"' in player
    assert ':repeat-current="loopMode === \'queue\' && tracks.length === 1"' in music
    assert 'if (loopMode.value === "queue" && tracks.value.length === 1) return;' in ended_block
    assert "if (tracks.value.length > 1)" in ended_block


def test_app_shell_keeps_the_music_audio_dom_mounted_across_authenticated_routes() -> None:
    shell = read_source("app/AppShell.vue")

    assert "defineAsyncComponent" in shell
    assert 'const MusicPage = defineAsyncComponent(() => import("../pages/MusicPage.vue"));' in shell
    assert "const musicMounted = ref(false);" in shell
    assert "watch(" in shell
    assert "musicMounted.value = true;" in shell
    assert '<MusicPage\n        v-if="musicMounted"' in shell
    assert 'v-show="activeNav === \'music\'"' in shell
    assert ':active="activeNav === \'music\'"' not in shell
    assert '<RouterView v-slot="{ Component }">' in shell
    assert '<component :is="Component" v-if="activeNav !== \'music\'" />' in shell
    assert "<KeepAlive" not in shell


def test_music_navigation_uses_playback_target_without_equalizer_animation() -> None:
    shell = read_source("app/AppShell.vue")

    assert 'import { usePlayerStore } from "../stores/player";' not in shell
    assert "const player = usePlayerStore();" not in shell
    assert 'id="music-nav-playback-target"' in shell
    assert 'class="music-nav-visualizer-target"' in shell
    assert 'class="creator-nav-content"' in shell
    assert "nav-playing-indicator" not in shell
    assert "@keyframes nav-playing-level" not in shell


def test_persistent_music_page_keeps_navigation_visualizer_bound_to_playback() -> None:
    music = read_source("pages/MusicPage.vue")

    assert ':playing="player.isPlaying"' in music
    assert "props.active" not in music


def test_music_page_mounts_static_playback_backdrop() -> None:
    package_json = read_frontend_file("package.json")
    music = read_source("pages/MusicPage.vue")
    shell = read_source("app/AppShell.vue")
    assert '"butterchurn"' not in package_json
    assert '"butterchurn-presets"' not in package_json
    assert 'import MusicPlaybackBackdrop from "../components/MusicPlaybackBackdrop.vue";' in music
    assert "const audioElement = ref(null);" not in music
    assert "function handleAudioReady(element)" not in music
    assert "function handleVisualizerError(message)" not in music
    assert "<MusicPlaybackBackdrop" in music
    assert ':playing="player.isPlaying"' in music
    assert '<Teleport to="#music-nav-playback-target">' in music
    assert 'class="music-nav-playback"' in music
    player_block = music.split('<YtsAudioPlayer', 1)[1].split('</YtsAudioPlayer>', 1)[0]
    assert '<MusicPlaybackBackdrop' not in player_block
    assert music.index('<MusicPlaybackBackdrop') < music.index('<article class="player-stage')
    assert 'id="music-nav-playback-target"' in shell
    assert '@audio-ready=' not in player_block


def test_playback_backdrop_uses_css_only_spinning_disc() -> None:
    backdrop_path = FRONTEND / "components/MusicPlaybackBackdrop.vue"
    assert backdrop_path.exists(), "playback backdrop is required"
    backdrop = backdrop_path.read_text(encoding="utf-8")

    assert "playing: { type: Boolean, default: false }" in backdrop
    assert "music-playback-backdrop" in backdrop
    assert 'class="playback-disc"' in backdrop
    assert ".music-playback-backdrop.active .playback-disc" in backdrop
    assert "animation: disc-spin 2400ms linear infinite;" in backdrop
    assert "@keyframes disc-spin" in backdrop
    assert "@media (prefers-reduced-motion: reduce)" in backdrop
    assert "AudioContext" not in backdrop
    assert "audioElement" not in backdrop
    assert "canvas" not in backdrop.lower()
    assert "setTimeout" not in backdrop
    assert "requestAnimationFrame" not in backdrop
    assert "butterchurn" not in backdrop.lower()
    assert "webgl" not in backdrop.lower()
    assert not (FRONTEND / "components/MusicButterchurnBackdrop.vue").exists()
    assert not (FRONTEND / "components/MusicSpectrumBackdrop.vue").exists()


def test_music_page_reads_existing_cover_without_starting_inference_during_playback() -> None:
    music = read_source("pages/MusicPage.vue")
    service = read_source("services/music.js")

    assert "ensureMusicCover" in service
    assert "deleteMusicCover" in service
    assert "regenerateMusicCover" in service
    assert 'if (environment.target !== "local")' in music
    assert "const response = await getMusicCoverStatus" in music
    assert "ensureMusicCover" not in music
    assert "await ensureInferenceReady(environment.target);" in music
    assert "coverLoadVersion" in music
    assert "responseContentHash !== track.contentHash" in music
    assert "scheduleCoverRefresh" in music


def test_music_page_exposes_delete_and_regenerate_generated_cover_controls() -> None:
    music = read_source("pages/MusicPage.vue")
    stage_path = FRONTEND / "components/MusicCoverStage.vue"

    assert stage_path.exists()
    stage = stage_path.read_text(encoding="utf-8")
    assert '<MusicCoverStage' in music
    assert "cover-panel" not in music
    assert "{{ coverState.error_message" not in music.split("<template>", 1)[1]
    assert 'class="cover-artwork"' in stage
    assert "aspect-ratio: 1 / 1;" in stage
    assert "object-fit: cover;" in stage
    assert 'class="track-context"' in stage
    assert "歌曲信息" not in stage
    assert 'class="lyrics-region"' in stage
    assert "暂无歌词" in stage
    assert "cover-vinyl" not in stage
    assert "vinyl-label" not in stage
    assert "正在后台生成封面" in stage
    assert "封面生成失败" in stage
    assert 'title="删除生成封面"' in stage
    assert 'title="重新生成封面"' in stage
    assert 'title="查看失败原因"' not in stage
    assert 'class="error-detail"' not in stage
    assert "detailsOpen" not in stage
    assert "@media (prefers-reduced-motion: reduce)" in stage
    status_rule = stage.split(".cover-status {", 1)[1].split("}", 1)[0]
    assert "border:" not in status_rule
    assert "color: #8da5b4;" in status_rule
    assert "本地图片模型未安装" in stage
    assert "handleDeleteCover" in music
    assert "handleRegenerateCover" in music
    assert "handleRetryCover" in music


def test_music_page_applies_persisted_cover_theme_without_canvas_sampling() -> None:
    music = read_source("pages/MusicPage.vue")

    assert "coverState.value.theme_color" in music
    assert "--cover-theme" in music
    assert ":theme-color=" in music
    assert "props.themeColor ? { \"--artwork-accent\": props.themeColor } : {}" in read_source(
        "components/MusicCoverStage.vue"
    )
    assert "Canvas" not in music
    assert "getImageData" not in music
    assert "createElement(\"canvas\")" not in music
    assert "ready cover is missing theme_color" in music
    assert "error.value = err instanceof Error ? err.message : String(err);" in music


def test_audio_player_uses_event_driven_native_controls_without_media_chrome() -> None:
    player = read_source("components/YtsAudioPlayer.vue")

    assert 'import "media-chrome";' not in player
    assert "<media-controller" not in player
    assert "<media-time-range" not in player
    assert "<media-control-bar" not in player
    assert "<media-play-button" not in player
    assert "<media-mute-button" not in player
    assert "<media-volume-range" not in player
    assert '<input\n        class="timeline-range"' in player
    assert '@input="handleSeekInput"' in player
    assert '@click="togglePlayback"' in player
    assert '@click="toggleMuted"' in player


def test_audio_player_timeline_has_cross_background_contrast() -> None:
    player = read_source("components/YtsAudioPlayer.vue")
    template = player.split("<template>", 1)[1].split("</template>", 1)[0]

    for token in [
        "appearance: none;",
        "-webkit-appearance: none;",
        '<span class="timeline-track">',
        '<span class="timeline-track-progress"></span>',
        ".timeline-track",
        ".timeline-track-progress",
        ".timeline-range::-webkit-slider-runnable-track",
        ".timeline-range::-webkit-slider-thumb",
        ".timeline-range::-moz-range-track",
        ".timeline-range::-moz-range-progress",
        ".timeline-range::-moz-range-thumb",
        "var(--timeline-progress)",
        "rgba(2, 8, 18, 0.92)",
        ".timeline-range:focus-visible::-webkit-slider-thumb",
    ]:
        assert token in player

    assert template.index('<span class="timeline-track">') < template.index(
        'class="timeline-range"'
    )

    timeline_track_rule = player.split(".timeline-track {", 1)[1].split("}", 1)[0]
    assert "height: 2px;" in timeline_track_rule
    assert "box-shadow:" not in timeline_track_rule
    assert "linear-gradient" not in timeline_track_rule

    timeline_progress_rule = player.split(".timeline-track-progress {", 1)[1].split("}", 1)[0]
    assert "background: var(--color-brand-cyan);" in timeline_progress_rule
    assert "width: var(--timeline-progress);" in timeline_progress_rule

    timeline_range_rule = player.split(".timeline-range {", 1)[1].split("}", 1)[0]
    for reset in ["border: 0;", "box-shadow: none;", "padding: 0;"]:
        assert reset in timeline_range_rule

    for selector in [
        ".timeline-range::-webkit-slider-runnable-track",
        ".timeline-range::-moz-range-track",
        ".timeline-range::-moz-range-progress",
    ]:
        rule = player.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "background: transparent;" in rule
        assert "border: 0;" in rule
        assert "box-shadow: none;" in rule
        assert "height: 2px;" in rule

    for selector in [
        ".timeline-range::-webkit-slider-thumb",
        ".timeline-range::-moz-range-thumb",
    ]:
        rule = player.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "height: 10px;" in rule
        assert "width: 10px;" in rule


def test_audio_player_volume_range_has_cross_background_contrast() -> None:
    player = read_source("components/YtsAudioPlayer.vue")

    for token in [
        ".volume-range {",
        "-webkit-appearance: none;",
        ".volume-range::-webkit-slider-runnable-track",
        ".volume-range::-webkit-slider-thumb",
        ".volume-range::-moz-range-track",
        ".volume-range::-moz-range-thumb",
        "background: rgba(237, 246, 255, 0.72);",
    ]:
        assert token in player

    for selector in [
        ".volume-range::-webkit-slider-runnable-track",
        ".volume-range::-moz-range-track",
    ]:
        rule = player.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "height: 2px;" in rule
        assert "background: rgba(237, 246, 255, 0.72);" in rule

    for selector in [
        ".volume-range::-webkit-slider-thumb",
        ".volume-range::-moz-range-thumb",
    ]:
        rule = player.split(f"{selector} {{", 1)[1].split("}", 1)[0]
        assert "height: 12px;" in rule
        assert "width: 12px;" in rule

    webkit_thumb_rule = player.split(
        ".volume-range::-webkit-slider-thumb {", 1
    )[1].split("}", 1)[0]
    assert "margin-top: -5px;" in webkit_thumb_rule
