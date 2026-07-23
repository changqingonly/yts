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

    assert "player.setQueue([]);" in unmount_block
    assert unmount_block.index("player.setQueue([]);") < unmount_block.index(
        "revokePlayableTrackUrls();"
    )


def test_music_page_refreshes_after_environment_change_without_manual_refresh_button() -> None:
    music = read_source("pages/MusicPage.vue")
    target_watch_block = music.split("watch(\n  () => environment.target", 1)[1].split(
        "\nonMounted(", 1
    )[0]

    assert "async (nextTarget, previousTarget) =>" in target_watch_block
    assert "if (nextTarget === previousTarget) return;" in target_watch_block
    assert "await refreshPlaylist();" in target_watch_block
    assert "RefreshCw" not in music
    assert 'title="刷新"' not in music
    assert 'aria-label="刷新"' not in music


def test_music_page_persists_and_restores_last_playback_position() -> None:
    music = read_source("pages/MusicPage.vue")
    player_store = read_source("stores/player.js")
    player = read_source("components/YtsAudioPlayer.vue")
    refresh_block = music.split("async function refreshPlaylist()", 1)[1].split(
        "async function loadPlayableTrackUrls", 1
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
    assert refresh_block.index("player.setQueue(tracks.value);") < refresh_block.index(
        "restorePlaybackResumeState();"
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


def test_playback_backdrop_has_no_continuous_runtime_work() -> None:
    backdrop_path = FRONTEND / "components/MusicPlaybackBackdrop.vue"
    assert backdrop_path.exists(), "static playback backdrop is required"
    backdrop = backdrop_path.read_text(encoding="utf-8")

    assert "playing: { type: Boolean, default: false }" in backdrop
    assert 'v-for="index in 3"' in backdrop
    assert "music-playback-backdrop" in backdrop
    assert "AudioContext" not in backdrop
    assert "audioElement" not in backdrop
    assert "canvas" not in backdrop.lower()
    assert "setTimeout" not in backdrop
    assert "requestAnimationFrame" not in backdrop
    assert "butterchurn" not in backdrop.lower()
    assert "webgl" not in backdrop.lower()
    assert not (FRONTEND / "components/MusicButterchurnBackdrop.vue").exists()
    assert not (FRONTEND / "components/MusicSpectrumBackdrop.vue").exists()


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
