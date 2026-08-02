from pathlib import Path


FRONTEND = Path("desktop/frontend/src")


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_welcome_exposes_starting_timeout_failure_and_actions() -> None:
    source = read_source("components/LocalStartupWelcome.vue")

    assert 'status === "starting"' in source
    assert 'status === "timeout"' in source
    assert 'status === "failed"' in source
    assert "本地服务启动较慢" in source
    assert "启动失败" in source
    assert '@click="$emit(\'retry\')"' in source
    assert '@click="$emit(\'continue\')"' in source
    assert "errorMessage" in source


def test_app_shell_renders_workspace_and_welcome_together() -> None:
    source = read_source("app/AppShell.vue")

    assert 'import LocalStartupWelcome from "../components/LocalStartupWelcome.vue";' in source
    assert "const localStartup = ref(" in source
    assert "const showLocalStartupWelcome = computed(" in source
    assert "<MusicPage" in source
    assert "<LocalStartupWelcome" in source
    assert '@startup-state="handleLocalStartupState"' in source
    assert '@retry="retryLocalStartup"' in source
    assert '@continue="dismissLocalStartupWelcome"' in source


def test_music_page_ready_requires_minimal_playlist_and_current_url() -> None:
    source = read_source("pages/MusicPage.vue")
    startup_block = source.split("async function beginLocalStartup", 1)[1].split(
        "function retryLocalStartup", 1
    )[0]

    assert "timeoutMs: 5000" in startup_block
    assert "prepare: async () =>" in startup_block
    assert "await refreshPlaylist();" in startup_block
    assert 'emit("startup-state", { status: "ready" });' in startup_block
    assert startup_block.index("await refreshPlaylist();") < startup_block.index(
        'status: "ready"'
    )
    assert 'error.stage === "timeout" ? "timeout" : "failed"' in startup_block
    assert "errorMessage:" in startup_block
    assert "defineExpose({ retryLocalStartup });" in source


def test_switching_to_local_restarts_the_welcome_state_machine() -> None:
    source = read_source("pages/MusicPage.vue")
    target_watch = source.split("() => environment.target,", 1)[1].split(
        "watch(\n  () => currentTrack.value", 1
    )[0]

    assert 'nextTarget === "local" && isTauriRuntime()' in target_watch
    assert "await beginLocalStartup({ reset: true });" in target_watch
