# Local Startup Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded local startup welcome flow that reaches first playable music quickly while keeping all failures explicit.

**Architecture:** A shared frontend startup coordinator owns sidecar startup, health, timeout, and minimal playlist readiness. AppShell renders the welcome state immediately; MusicPage consumes the prepared playlist and loads only the current track URL on the critical path. Non-critical playlist metadata and model gateway startup remain outside the startup path.

**Tech Stack:** Vue 3, Pinia, Tauri invoke, existing transport/music services, pytest source-contract tests.

## Global Constraints

- Window/workspace rendering must not wait for sidecar health or playlist data.
- A shared Promise must deduplicate sidecar startup and health checks.
- `ready` requires health, minimal playlist data, and the current track URL when a ready track exists.
- Startup renders loading immediately and uses a 30-second foreground wait window; timeout keeps the underlying readiness task available for explicit continued waiting.
- `infer-gateway` remains explicit-operation-only.
- Preserve existing strict validation and explicit errors; do not add fallback data.

### Task 1: Add Shared Local Startup Coordinator

**Files:**
- Create: `desktop/frontend/src/services/localStartup.js`
- Modify: `desktop/frontend/src/services/desktop.js`
- Modify: `desktop/frontend/src/stores/environment.js`
- Test: `tests/test_local_startup_flow.py`

**Interfaces:**
- `startLocalPlayback({ target = "local", timeoutMs = 30000 } = {}) -> Promise<LocalStartupResult>` returns `{ status: "ready", target }` or rejects with an explicit startup error carrying `stage`.
- `resetLocalPlaybackStartup()` clears only completed/failed coordinator state for an explicit retry.
- The coordinator calls existing `startSidecar()`, `healthCheck(target)`, `playlistStore.loadMinimal(...)`, and `loadSongObjectUrl(...)` through injected callbacks so tests can assert ordering without network access.

- [ ] **Step 1: Write failing source-contract tests** asserting one shared Promise for concurrent calls, a 30000ms timeout, failure stage propagation, and no `startGateway` import/call in the coordinator.
- [ ] **Step 2: Run `pytest tests/test_local_startup_flow.py -q` and confirm the new contracts fail.**
- [ ] **Step 3: Implement coordinator state with one module-level Promise per target; race the minimal readiness Promise against a 30000ms foreground timer, clear the timer, and retain the underlying readiness task for continued waiting.**
- [ ] **Step 4: Update environment health calls to reuse the coordinator's sidecar/health Promise rather than spawning another sidecar.**
- [ ] **Step 5: Run the focused test and existing environment lifecycle tests; commit `feat: coordinate local playback startup`.**

### Task 2: Split Minimal Playlist Loading From Background Metadata

**Files:**
- Modify: `desktop/frontend/src/stores/playlist.js`
- Modify: `desktop/frontend/src/pages/MusicPage.vue`
- Modify: `desktop/frontend/src/services/music.js` only if an existing request helper cannot express the minimal load
- Test: `tests/test_music_page_lifecycle.py`

**Interfaces:**
- `playlist.hydrateMinimal({ scope })` loads playlists, selects/creates the default playlist, and loads active playlist items; it does not load deleted items.
- `playlist.loadBackgroundMetadata({ playlistId })` loads deleted items and records an explicit `lastError` on rejection before rethrowing.
- `MusicPage` exposes `prepareInitialPlayback()` for the coordinator and uses `loadPlayableTrackUrl` only for the current track during startup.

- [ ] **Step 1: Add failing tests asserting `hydrateMinimal` excludes `loadDeletedItems`, startup awaits only `loadCurrentTrackUrl`, and deleted-item loading is scheduled after ready.**
- [ ] **Step 2: Run the targeted lifecycle tests and confirm failure.**
- [ ] **Step 3: Implement the two playlist actions by moving the existing sequential calls without changing normalization or validation.**
- [ ] **Step 4: Change MusicPage mount flow to consume prepared minimal data, load only the current ready track URL, then schedule background metadata/rendition/cover work.**
- [ ] **Step 5: Run `pytest tests/test_music_page_lifecycle.py -q`; commit `perf: load only first playable track during startup`.**

### Task 3: Render Welcome Page With Explicit States

**Files:**
- Create: `desktop/frontend/src/components/LocalStartupWelcome.vue`
- Modify: `desktop/frontend/src/app/AppShell.vue`
- Modify: `desktop/frontend/src/router/index.js` only if route rendering requires a startup gate
- Test: `tests/test_frontend_local_startup_welcome.py`

**Interfaces:**
- Welcome component accepts `status`, `stage`, `errorMessage`, and `onRetry`; it renders starting, ready transition, failed, and timeout states without hiding the underlying error.
- AppShell starts the coordinator on mount, renders workspace shell immediately, and switches `musicMounted` only after ready or explicit user action from failed/timeout.

- [ ] **Step 1: Add failing source tests for immediate shell rendering, 30-second timeout copy/state, continued-wait action, and explicit terminal failure text.**
- [ ] **Step 2: Run the focused test and confirm failure.**
- [ ] **Step 3: Implement the welcome component using existing CSS tokens and compact loading/error states; do not add a blocking full-screen network spinner without an actionable error state.**
- [ ] **Step 4: Wire AppShell to the coordinator, keep `environment.checkHealth` fire-and-forget for status updates, and remove duplicate startup waits from MusicPage mount.**
- [ ] **Step 5: Run frontend lifecycle/layout tests; commit `feat: add local startup welcome state`.**

### Task 4: Regression and Verification

**Files:**
- Modify: `tests/test_environment_health_lifecycle.py` if assertions need updated startup ownership
- Modify: `tests/test_local_gateway_startup.py` only to preserve gateway isolation assertions
- Add/modify: `tests/test_frontend_local_startup_welcome.py`, `tests/test_local_startup_flow.py`

- [ ] **Step 1: Run focused Python tests for startup, music lifecycle, environment health, and gateway isolation.**
- [ ] **Step 2: Run the full test suite with `pytest -q`.**
- [ ] **Step 3: Run frontend package checks/build from `desktop/frontend` using the existing package manager scripts.**
- [ ] **Step 4: Inspect `git diff` for accidental changes to untracked user files and verify no gateway startup was added to AppShell/MusicPage.**
- [ ] **Step 5: Commit verification-only test updates if needed and report measured startup behavior and any environment-limited checks.**
