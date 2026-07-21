# Desktop Background Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep LeTu services running when the main window closes, while guaranteeing that application Quit and abrupt Tauri termination remove every instance-owned service and producer within three seconds.

**Architecture:** The Tauri process remains the background controller and exposes an authenticated, instance-scoped Unix socket to the packaged sidecar and gateway. Normal Quit sends a structured shutdown command; abrupt controller death closes the socket, causing the children to enter the same shutdown path. The gateway launches every native producer in a distinct Unix process group and owns termination and reaping.

**Tech Stack:** Rust 2021, Tauri 2.11, Tokio, Axum, Unix domain sockets/process groups, Python 3.10+, Uvicorn, pytest

## Global Constraints

- Closing the red macOS window button hides the GUI and keeps playback and generation services running.
- Application-menu Quit and status-item Quit execute the same shutdown operation.
- `SIGKILL` of Tauri must cause every instance-owned PID, process group, and ports 8765/8799 to disappear within three seconds.
- The Unix socket is the only abnormal-parent-death signal; do not add parent-PID polling or process-name scanning.
- Never use `pkill -f`, executable-name matching, or port ownership to select a process for termination.
- Cleanup errors, deadline escalation, malformed IPC, and logging failures must be explicit; do not silently downgrade them.
- Development `servctl`, Docker Desktop, and unrelated application instances must remain untouched.
- Do not add a LaunchAgent or login startup.

---

### Task 1: Application State Machine And Menu Bar Shell

**Files:**
- Create: `desktop/src-tauri/src/app_lifecycle.rs`
- Modify: `desktop/src-tauri/src/lib.rs`
- Modify: `desktop/src-tauri/Cargo.toml`

**Interfaces:**
- Produces: `AppLifecycle::new()`, `AppLifecycle::phase()`, `AppLifecycle::begin_stopping()`, `AppLifecycle::mark_stopped()`
- Produces: `show_main_window(&AppHandle) -> Result<(), String>` and one shared `request_quit(AppHandle)` entry point
- Consumes later: `lifecycle_ipc::LifecycleServer::shutdown(Duration)` from Task 2

- [ ] **Step 1: Write failing state transition tests**

Create `app_lifecycle.rs` with tests first:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn first_quit_request_enters_stopping_and_repeats_are_idempotent() {
        let state = AppLifecycle::new();
        assert!(state.begin_stopping());
        assert!(!state.begin_stopping());
        assert_eq!(state.phase(), AppPhase::Stopping);
    }

    #[test]
    fn stopped_state_allows_the_tauri_event_loop_to_exit() {
        let state = AppLifecycle::new();
        assert!(state.begin_stopping());
        state.mark_stopped();
        assert_eq!(state.phase(), AppPhase::Stopped);
    }
}
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cargo test --manifest-path desktop/src-tauri/Cargo.toml app_lifecycle::tests -- --nocapture
```

Expected: compilation fails because `AppLifecycle` and `AppPhase` are undefined.

- [ ] **Step 3: Implement the minimal atomic state machine**

Implement an `AtomicU8`-backed state with exactly these public types:

```rust
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AppPhase { Running, Stopping, Stopped }

pub struct AppLifecycle(AtomicU8);

impl AppLifecycle {
    pub const fn new() -> Self;
    pub fn phase(&self) -> AppPhase;
    pub fn begin_stopping(&self) -> bool;
    pub fn mark_stopped(&self);
}
```

Use `compare_exchange` for `Running -> Stopping`; invalid numeric state is a hard panic because it indicates internal corruption.

- [ ] **Step 4: Wire window close, reopen, and tray commands**

Enable Tauri's `tray-icon` feature. In `setup`, build a tray menu with IDs `open-main-window` and `quit-application`, using the configured application icon. Add helpers with these behaviors:

```rust
fn show_main_window(app: &tauri::AppHandle) -> Result<(), String> {
    let window = app.get_webview_window("main").ok_or("main window is missing")?;
    window.show().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())
}
```

In the run callback:

- `WindowEvent::CloseRequested` on `main` while `Running`: call `api.prevent_close()` and `window.hide()`.
- `RunEvent::Reopen`: show and focus `main`.
- tray `open-main-window`: show and focus `main`.
- tray `quit-application` and `RunEvent::ExitRequested` while `Running`: prevent immediate exit and call the shared `request_quit` function.
- `RunEvent::ExitRequested` while `Stopping`: prevent duplicate exit.
- `RunEvent::ExitRequested` while `Stopped`: allow exit.

Do not add playback controls or any LaunchAgent behavior.

- [ ] **Step 5: Run focused tests and commit**

```bash
cargo fmt --manifest-path desktop/src-tauri/Cargo.toml -- --check
cargo test --manifest-path desktop/src-tauri/Cargo.toml app_lifecycle::tests
git add desktop/src-tauri/Cargo.toml desktop/src-tauri/Cargo.lock \
  desktop/src-tauri/src/app_lifecycle.rs desktop/src-tauri/src/lib.rs
git commit -m "feat: keep desktop controller alive after window close"
```

Expected: state tests pass and the Tauri crate compiles with tray support.

---

### Task 2: Authenticated Tauri Lifecycle Socket

**Files:**
- Create: `desktop/src-tauri/src/lifecycle_ipc.rs`
- Modify: `desktop/src-tauri/src/lib.rs`
- Modify: `desktop/src-tauri/src/sidecar.rs`
- Modify: `desktop/src-tauri/src/gateway.rs`
- Modify: `desktop/src-tauri/Cargo.toml`

**Interfaces:**
- Produces: `LifecycleServer::bind(runtime_dir, log_path) -> Result<Self, LifecycleError>`
- Produces: `LifecycleServer::child_env(component) -> BTreeMap<String, String>`
- Produces: `LifecycleServer::wait_registered(component, timeout) -> Result<(), LifecycleError>`
- Produces: `LifecycleServer::shutdown(deadline) -> Result<ShutdownReport, LifecycleError>`
- Consumes: component names `yts-sidecar` and `infer-gateway`

- [ ] **Step 1: Write failing protocol tests with real Unix sockets**

Add Tokio tests that bind under a temporary directory and exercise a real client:

```rust
#[tokio::test]
async fn rejects_a_client_with_the_wrong_instance_token() {
    let server = test_server().await;
    let mut client = UnixStream::connect(server.socket_path()).await.unwrap();
    client.write_all(br#"{"schema_version":1,"type":"hello","component":"yts-sidecar","token":"wrong"}\n"#).await.unwrap();
    let mut response = String::new();
    BufReader::new(client).read_line(&mut response).await.unwrap();
    assert!(response.contains("token mismatch"));
    assert!(server.wait_registered("yts-sidecar", Duration::from_millis(50)).await.is_err());
}

#[tokio::test]
async fn shutdown_waits_for_registered_components_to_acknowledge_stopped() {
    let server = test_server().await;
    let client = spawn_fake_component(&server, "infer-gateway").await;
    server.wait_registered("infer-gateway", Duration::from_secs(1)).await.unwrap();
    let report = server.shutdown(Instant::now() + Duration::from_secs(1)).await.unwrap();
    client.await.unwrap();
    assert_eq!(report.stopped, vec!["infer-gateway"]);
}
```

The fake component validates `registered`, waits for `shutdown`, replies with `stopped`, and closes.

- [ ] **Step 2: Run the tests and verify RED**

```bash
cargo test --manifest-path desktop/src-tauri/Cargo.toml lifecycle_ipc::tests -- --nocapture
```

Expected: compilation fails because `LifecycleServer` is undefined.

- [ ] **Step 3: Implement the framed protocol and server**

Use newline-delimited JSON with these exact messages:

```rust
#[derive(Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum ClientMessage {
    Hello { schema_version: u32, component: String, token: String },
    Stopped { schema_version: u32, component: String, errors: Vec<String> },
}

#[derive(Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum ServerMessage {
    Registered { schema_version: u32 },
    Shutdown { schema_version: u32, remaining_millis: u64 },
    Error { schema_version: u32, message: String },
}
```

Generate a 32-byte random token with `rand::rngs::OsRng`. Store one command channel and one stopped notification per authenticated component. Reject unknown components, duplicate registrations, schema versions other than 1, and tokens that do not match. Remove the instance-specific socket file on `Drop`; use a PID plus random suffix so stale files cannot collide with another launch.

- [ ] **Step 4: Pass explicit managed-mode environment to children**

Add these variables to both packaged child commands:

```text
YTS_LIFECYCLE_MODE=managed
YTS_LIFECYCLE_SOCKET=<absolute socket path>
YTS_LIFECYCLE_TOKEN=<instance token>
YTS_LIFECYCLE_COMPONENT=<yts-sidecar|infer-gateway>
YTS_DESKTOP_LOG_PATH=<absolute yts-desktop.log path>
YTS_INSTANCE_ID=<random instance identifier>
```

After spawn, `start_sidecar` and `start_gateway` await authenticated registration before returning success. A registration timeout kills the exact newly spawned `CommandChild`, waits for its termination event, clears state, and returns the error. Remove every ignored `let _ =` from start/stop/restart control flow.

- [ ] **Step 5: Make normal Quit wait once on a shared deadline**

Implement `request_quit` to call `LifecycleServer::shutdown(Instant::now() + Duration::from_secs(3))`, then wait for both top-level `CommandEvent::Terminated` notifications using only the remaining deadline. On success mark `Stopped` and call `app.exit(0)`. On lifecycle errors, log the structured report, terminate only the stored exact children, mark `Stopped`, and call `app.exit(1)`.

Delete `kill_children` and its `pkill -9 -f` block completely.

- [ ] **Step 6: Verify and commit**

```bash
cargo fmt --manifest-path desktop/src-tauri/Cargo.toml -- --check
cargo test --manifest-path desktop/src-tauri/Cargo.toml lifecycle_ipc::tests
cargo test --manifest-path desktop/src-tauri/Cargo.toml
git add desktop/src-tauri/Cargo.toml desktop/src-tauri/Cargo.lock desktop/src-tauri/src
git commit -m "feat: supervise packaged services over lifecycle ipc"
```

Expected: all Tauri tests pass; source contains no `pkill` or ignored child-kill result.

---

### Task 3: Managed Python Sidecar Shutdown

**Files:**
- Create: `desktop/sidecar/lifecycle.py`
- Create: `tests/test_desktop_sidecar_lifecycle.py`
- Modify: `desktop/sidecar/app.py`
- Modify: `desktop/sidecar/build_macos.spec`

**Interfaces:**
- Produces: `LifecycleConfig.from_environ(environ) -> LifecycleConfig | None`
- Produces: `run_managed(server: uvicorn.Server, config: LifecycleConfig) -> None`
- Consumes: Task 2 JSON-line protocol and `YTS_LIFECYCLE_*` variables

- [ ] **Step 1: Write failing configuration and EOF tests**

Write tests using an actual temporary Unix server and a fake Uvicorn object:

```python
def test_managed_mode_requires_every_lifecycle_variable() -> None:
    with pytest.raises(LifecycleConfigurationError, match="YTS_LIFECYCLE_SOCKET"):
        LifecycleConfig.from_environ({"YTS_LIFECYCLE_MODE": "managed"})

@pytest.mark.asyncio
async def test_lifecycle_eof_requests_server_shutdown(tmp_path: Path) -> None:
    fake = FakeServer()
    socket_path, controller = await start_fake_controller(tmp_path, close_after_registration=True)
    config = lifecycle_config(socket_path)
    await run_managed(fake, config)
    await controller
    assert fake.should_exit is True
```

`FakeServer.serve()` blocks until `should_exit` becomes true and records that it completed.

- [ ] **Step 2: Run the tests and verify RED**

```bash
.tools/uv/uv run pytest tests/test_desktop_sidecar_lifecycle.py -v
```

Expected: import fails because `desktop.sidecar.lifecycle` does not exist.

- [ ] **Step 3: Implement the sidecar lifecycle client**

`LifecycleConfig.from_environ` has two explicit modes: missing/`standalone` for development and `managed` for the packaged app. Managed mode requires all lifecycle variables and rejects incomplete configuration.

`run_managed` must connect before Uvicorn starts, authenticate, run Uvicorn and the lifecycle reader concurrently, set `server.should_exit = True` on `shutdown` or EOF, wait for `server.serve()` to return, verify the listener is closed, and reply `stopped` only on the normal command path. It appends malformed protocol, timeout, and shutdown failures directly to `YTS_DESKTOP_LOG_PATH` with `YTS_INSTANCE_ID`.

Use `asyncio.run`; do not call `uvicorn.run`, because its internal loop is not externally controllable.

- [ ] **Step 4: Update the executable entry point and PyInstaller inputs**

Construct `uvicorn.Config` and `uvicorn.Server` in `app.py`. Call standalone `server.run()` only when the explicit lifecycle mode is standalone; call `asyncio.run(run_managed(server, config))` in managed mode. Include `lifecycle.py` in the PyInstaller analysis path/imports.

- [ ] **Step 5: Verify and commit**

```bash
.tools/uv/uv run pytest tests/test_desktop_sidecar_lifecycle.py -v
.tools/uv/uv run ruff check desktop/sidecar tests/test_desktop_sidecar_lifecycle.py
.tools/uv/uv run ruff format --check desktop/sidecar tests/test_desktop_sidecar_lifecycle.py
git add desktop/sidecar tests/test_desktop_sidecar_lifecycle.py
git commit -m "feat: stop desktop sidecar when controller disappears"
```

Expected: lifecycle tests pass and managed startup cannot continue without an authenticated controller.

---

### Task 4: Gateway Lifeline And Producer Process Groups

**Files:**
- Create: `desktop/infer-gateway/src/lifecycle.rs`
- Create: `desktop/infer-gateway/src/process_group.rs`
- Modify: `desktop/infer-gateway/src/main.rs`
- Modify: `desktop/infer-gateway/src/llama.rs`
- Modify: `desktop/infer-gateway/src/image.rs`
- Modify: `desktop/infer-gateway/src/stream.rs`
- Modify: `desktop/infer-gateway/Cargo.toml`

**Interfaces:**
- Produces: `LifecycleClient::connect_from_env() -> Result<Option<Self>>`
- Produces: `LifecycleClient::shutdown_signal() -> watch::Receiver<ShutdownReason>`
- Produces: `ProcessRegistry::spawn(kind, request_id, command) -> Result<OwnedChild>`
- Produces: `ProcessRegistry::shutdown(deadline) -> Result<ShutdownReport>`
- Consumes: Task 2 protocol and managed environment

- [ ] **Step 1: Write failing real-process tests**

```rust
#[tokio::test]
async fn signaling_an_owned_group_terminates_shell_and_descendant() {
    let registry = ProcessRegistry::default();
    let mut command = Command::new("sh");
    command.args(["-c", "sleep 30 & wait"]);
    let child = registry.spawn("test", "nested", command).await.unwrap();
    let pgid = child.pgid();
    registry.shutdown(Instant::now() + Duration::from_secs(2)).await.unwrap();
    assert!(!process_group_exists(pgid).unwrap());
}

#[tokio::test]
async fn lifecycle_eof_broadcasts_abnormal_shutdown() {
    let (client, controller) = connected_test_lifecycle().await;
    drop(controller);
    let mut signal = client.shutdown_signal();
    signal.changed().await.unwrap();
    assert_eq!(*signal.borrow(), ShutdownReason::ControllerDisconnected);
}
```

- [ ] **Step 2: Run the tests and verify RED**

```bash
cargo test --manifest-path desktop/infer-gateway/Cargo.toml process_group::tests lifecycle::tests -- --nocapture
```

Expected: compilation fails because both modules are absent.

- [ ] **Step 3: Implement exact process-group ownership**

Before each spawn, call Tokio `Command::process_group(0)` and `kill_on_drop(true)`. After spawn, require `child.id()` and use it as the PGID. Register `{kind, request_id, pid, pgid}` before returning.

Use `libc::kill(-pgid, signal)` only with positive PGIDs obtained from a successful owned spawn. Treat `ESRCH` as already stopped; propagate every other OS error. `OwnedChild::wait()` reaps the child and unregisters it. `ProcessRegistry::shutdown` sends `SIGTERM`, waits concurrently, records deadline escalation, sends `SIGKILL` only to remaining registered groups, and reaps them before returning. Add direct `libc = "0.2"`; do not invoke `/bin/kill` or `pkill`.

- [ ] **Step 4: Route all producer launches through the registry**

- `LlamaBackend::start(registry)` returns `Result<Self>` and fails if spawn or readiness fails; remove the current log-and-continue path and readiness warning continuation.
- `image::gen_image` receives `State<GatewayState>` and launches its shell through the registry.
- `stream::music_stream_handler` receives the same state and launches audio producers through the registry.
- Use unique temporary output paths containing the request ID, and propagate file removal failures after successful reads.
- On WebSocket stop/disconnect or request cancellation, terminate and reap that request's exact producer group.

Define shared router state:

```rust
#[derive(Clone)]
pub struct GatewayState {
    pub llama: LlamaBackend,
    pub processes: ProcessRegistry,
}
```

- [ ] **Step 5: Add lifecycle-driven Axum shutdown**

In managed mode, connect and authenticate before binding port 8799. Run Axum with `with_graceful_shutdown` driven by the lifecycle signal. After Axum stops, call `processes.shutdown(deadline)`, send `stopped` only if the controller issued normal shutdown and the report has no errors, then exit. In standalone development mode, preserve Ctrl-C shutdown but still route producers through the registry.

- [ ] **Step 6: Verify and commit**

```bash
cargo fmt --manifest-path desktop/infer-gateway/Cargo.toml -- --check
cargo test --manifest-path desktop/infer-gateway/Cargo.toml -- --nocapture
cargo clippy --manifest-path desktop/infer-gateway/Cargo.toml --all-targets -- -D warnings
git add desktop/infer-gateway/Cargo.toml desktop/infer-gateway/Cargo.lock desktop/infer-gateway/src
git commit -m "feat: bind gateway producers to controller lifecycle"
```

Expected: nested shell descendants are gone after shutdown and lifecycle EOF stops the gateway.

---

### Task 5: Packaged macOS Lifecycle Acceptance

**Files:**
- Create: `scripts/test_desktop_lifecycle_macos.sh`
- Modify: `scripts/build_desktop_macos.sh`
- Modify: `README.md`
- Modify: `tests/test_environment_health_lifecycle.py`

**Interfaces:**
- Consumes: packaged `乐兔.app`, lifecycle log records, ports 8765/8799
- Produces: one non-interactive acceptance command that exits nonzero on any leaked owned PID/PGID/port

- [ ] **Step 1: Write the failing acceptance script contract test**

```python
def test_packaged_desktop_lifecycle_script_uses_instance_owned_processes() -> None:
    source = (_REPO_ROOT / "scripts" / "test_desktop_lifecycle_macos.sh").read_text()
    assert "YTS_INSTANCE_ID" in source
    assert 'kill -9 "${app_pid}"' in source
    assert "deadline" in source
    assert "pkill" not in source
    assert "killall" not in source
```

- [ ] **Step 2: Run the contract test and verify RED**

```bash
.tools/uv/uv run pytest tests/test_environment_health_lifecycle.py::test_packaged_desktop_lifecycle_script_uses_instance_owned_processes -v
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Implement the packaged acceptance script**

The script builds/installs the current `.app`, launches it through `open`, reads the current instance's structured lifecycle records, and uses only recorded PIDs/PGIDs for assertions. It starts local services, closes the main window with AppleScript and proves ports remain live, reopens the app, triggers normal Quit and checks the three-second deadline, repeats with `kill -9 "${app_pid}"`, and proves any pre-existing development `servctl` PID remains unchanged. Every failure prints instance ID, PID, PGID, port, and recent lifecycle records and exits nonzero.

- [ ] **Step 4: Document behavior and integrate optional packaged verification**

Update README's macOS packaging section with the exact close-versus-Quit behavior and this command:

```bash
bash scripts/test_desktop_lifecycle_macos.sh
```

Have `build_desktop_macos.sh` print the command after a successful build; do not automatically launch or terminate the user's installed application during a normal build.

- [ ] **Step 5: Run full verification**

```bash
.tools/uv/uv run pytest tests/test_desktop_sidecar_lifecycle.py \
  tests/test_environment_health_lifecycle.py -v
.tools/uv/uv run ruff check desktop/sidecar tests scripts
cargo test --manifest-path desktop/src-tauri/Cargo.toml
cargo test --manifest-path desktop/infer-gateway/Cargo.toml
cargo clippy --manifest-path desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
cargo clippy --manifest-path desktop/infer-gateway/Cargo.toml --all-targets -- -D warnings
git diff --check
```

Expected: all focused Python and Rust tests pass, both Clippy runs are warning-free, and diff check has no output.

- [ ] **Step 6: Build and exercise the real application**

```bash
bash scripts/build_desktop_macos.sh
bash scripts/test_desktop_lifecycle_macos.sh
```

Expected: the real packaged app passes window-close, normal-Quit, and `SIGKILL` scenarios; all owned processes and ports disappear within three seconds in both exit scenarios.

- [ ] **Step 7: Commit documentation and acceptance coverage**

```bash
git add README.md scripts/build_desktop_macos.sh scripts/test_desktop_lifecycle_macos.sh \
  tests/test_environment_health_lifecycle.py
git commit -m "test: verify packaged desktop process cleanup"
```
