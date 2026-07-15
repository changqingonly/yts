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
    assert "wasPlaying: player.isPlaying" in music
    assert "player.setQueue(tracks.value);" in refresh_block
    assert "restorePlaybackResumeState();" in refresh_block
    assert refresh_block.index("player.setQueue(tracks.value);") < refresh_block.index(
        "restorePlaybackResumeState();"
    )
    assert (
        "player.selectAt(resumeIndex, { currentTime: resumeState.currentTime, isPlaying: resumeState.wasPlaying });"
        in music
    )
    assert "resumeSeekTime.value = resumeState.currentTime;" in music
    assert "writePlaybackResumeState(currentTrack.value, currentTime);" in time_update_block
    assert "selectAt(index, { currentTime = 0, isPlaying = false } = {})" in player_store
    assert "this.isPlaying = Boolean(isPlaying);" in player_store
    assert ':seek-time="resumeSeekTime"' in music
    assert '@seek-applied="handleSeekApplied"' in music
    assert 'seekTime: { type: Number, default: null }' in player
    assert '"seek-applied"' in player


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


def test_music_page_mounts_butterchurn_backdrop_from_audio_player_element() -> None:
    package_json = read_frontend_file("package.json")
    music = read_source("pages/MusicPage.vue")
    player = read_source("components/YtsAudioPlayer.vue")

    assert '"butterchurn"' in package_json
    assert '"butterchurn-presets"' in package_json
    assert 'import MusicButterchurnBackdrop from "../components/MusicButterchurnBackdrop.vue";' in music
    assert "const audioElement = ref(null);" in music
    assert "function handleAudioReady(element)" in music
    assert "audioElement.value = element;" in music
    assert "function handleVisualizerError(message)" in music
    assert "error.value = message;" in music
    assert "<MusicButterchurnBackdrop" in music
    assert ':audio-element="audioElement"' in music
    assert ':playing="player.isPlaying"' in music
    assert '@visualizer-error="handleVisualizerError"' in music
    assert "class=\"butterchurn-backdrop\"" in music
    assert music.index("<MusicButterchurnBackdrop") < music.index('<article class="player-stage')
    assert '@audio-ready="handleAudioReady"' in music
    assert '"audio-ready"' in player
    assert 'emit("audio-ready", requireAudio());' in player


def test_butterchurn_backdrop_uses_explicit_webgl_lifecycle_without_fallback() -> None:
    visualizer_path = FRONTEND / "components/MusicButterchurnBackdrop.vue"

    assert visualizer_path.exists()
    visualizer = visualizer_path.read_text(encoding="utf-8")

    assert 'import("butterchurn")' in visualizer
    assert 'import("butterchurn-presets")' in visualizer
    assert 'audioElement: { type: Object, default: null }' in visualizer
    assert 'playing: { type: Boolean, default: false }' in visualizer
    assert '"visualizer-error"' in visualizer
    assert 'canvasRef.value.getContext("webgl2", WEBGL_OPTIONS)' in visualizer
    assert "当前浏览器不支持 WebGL2 动态背景" in visualizer
    assert "new AudioContext()" in visualizer
    assert "audioContext.value.createMediaElementSource(props.audioElement)" in visualizer
    assert "butterchurn.value.createVisualizer(audioContext.value, canvasRef.value" in visualizer
    assert "visualizer.value.connectAudio(sourceNode.value)" in visualizer
    assert "butterchurnPresets.value.getPresets()" in visualizer
    assert "visualizer.value.loadPreset(selectedPreset, 0)" in visualizer
    assert "visualizer.value.render()" in visualizer
    assert "requestAnimationFrame(renderFrame)" in visualizer
    assert "cancelAnimationFrame(animationFrameId)" in visualizer
    assert "function destroyVisualizer()" in visualizer
    assert "fallback" not in visualizer.lower()


def test_butterchurn_backdrop_uses_full_spectrum_composition_without_hue_rotation() -> None:
    visualizer = read_source("components/MusicButterchurnBackdrop.vue")
    style = visualizer.split("<style scoped>", 1)[1].split("</style>", 1)[0]
    normal_style, reduced_motion_style = style.split(
        "@media (prefers-reduced-motion: reduce)", 1
    )

    active = css_declarations(normal_style, ".music-butterchurn-backdrop.active")
    overlay = css_declarations(normal_style, ".music-butterchurn-backdrop::after")
    canvas = css_declarations(normal_style, ".music-butterchurn-backdrop canvas")
    reduced_motion_active = css_declarations(
        reduced_motion_style, ".music-butterchurn-backdrop.active"
    )

    assert active["opacity"] == "0.9"
    assert canvas["filter"].split() == ["saturate(1.5)", "contrast(1.08)"]
    assert overlay["background"] == (
        "radial-gradient(circle at 50% 42%, transparent 0 64%, "
        "rgba(4, 11, 21, 0.24) 100%), "
        "linear-gradient(180deg, rgba(4, 11, 21, 0.02), "
        "rgba(4, 11, 21, 0.18))"
    )
    assert reduced_motion_active["opacity"] == "0"
