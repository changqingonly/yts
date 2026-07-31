# Music Local Startup Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate initial and target-switch playlist requests on the selected environment becoming healthy.

**Architecture:** Add one readiness-gated refresh function in `MusicPage.vue` that joins the environment store's existing health-check promise. Route mount and target-change flows through it while preserving the existing playlist request and error formatter.

**Tech Stack:** Vue 3, Pinia, pytest source-level frontend tests, Vite

## Global Constraints

- Do not show a playlist error while target health is `checking`.
- Show a connection failure only after health resolves to `offline`.
- Ignore stale readiness results after a target switch.
- Do not add fallback or silent error handling.

---

### Task 1: Gate playlist refresh on target readiness

**Files:**
- Modify: `tests/test_music_page_lifecycle.py`
- Modify: `desktop/frontend/src/pages/MusicPage.vue`

**Interfaces:**
- Consumes: `environment.checkHealth(target): Promise<"online" | "offline">`.
- Produces: `refreshPlaylistWhenTargetReady(target): Promise<void>`.

- [ ] **Step 1: Add a failing lifecycle test**

Assert that the new function clears the prior error, awaits `environment.checkHealth(target)`, rejects stale target results, reports explicit offline status, and only then calls `refreshPlaylist()`. Assert mount and target-watch flows call this function instead of directly refreshing.

- [ ] **Step 2: Verify the test fails**

Run: `./.venv/bin/pytest tests/test_music_page_lifecycle.py::test_music_page_waits_for_target_health_before_loading_playlist -q`

Expected: FAIL because the readiness-gated function does not exist.

- [ ] **Step 3: Implement the readiness gate**

Add `refreshPlaylistWhenTargetReady(target = environment.target)` to `MusicPage.vue`. Await the health check, ignore stale results, format an explicit offline error, and call `refreshPlaylist()` only for `online`.

- [ ] **Step 4: Route lifecycle entry points through the gate**

Pass `nextTarget` from the environment target watcher and replace the direct mount refresh with `refreshPlaylistWhenTargetReady()`.

- [ ] **Step 5: Verify tests and build**

Run: `./.venv/bin/pytest tests/test_music_page_lifecycle.py -q`

Expected: PASS.

Run: `PATH=/Users/bytedance/Documents/projects/yts/.tools/node/bin:$PATH npm run build`

Working directory: `desktop/frontend`

Expected: Vite exits with status 0.
