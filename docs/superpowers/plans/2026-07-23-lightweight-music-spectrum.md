# Static Music Playback Backdrop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Butterchurn with a zero-loop playback-state background in the music navigation item.

**Architecture:** A Vue component renders three fixed bars and changes opacity only when playback state changes. MusicPage passes only `playing`; no audio graph, Canvas, timer, or animation frame remains.

**Tech Stack:** Vue 3, CSS, pytest source-contract tests, Vite, Tauri 2.

## Global Constraints

- Preserve native audio playback behavior.
- Perform no continuous visual work while playing, paused, or hidden.
- Do not add fallback or silent degradation paths.
- Preserve unrelated dirty-worktree changes.

---

### Task 1: Static playback component

**Files:**
- Create: `desktop/frontend/src/components/MusicPlaybackBackdrop.vue`
- Modify: `tests/test_music_page_lifecycle.py`

**Interfaces:**
- Consumes: `playing: boolean`
- Produces: a static active/inactive visual state

- [ ] Write a failing source-contract test requiring three fixed bars and prohibiting Web Audio, Canvas, timers, and animation frames.
- [ ] Run `pytest tests/test_music_page_lifecycle.py -q` and verify failure because the component does not exist.
- [ ] Implement the component with a prop-driven class and static CSS.
- [ ] Run the focused lifecycle tests and Ruff until they pass.

### Task 2: Replace Butterchurn wiring

**Files:**
- Modify: `desktop/frontend/src/pages/MusicPage.vue`
- Delete: `desktop/frontend/src/components/MusicButterchurnBackdrop.vue`
- Delete: `desktop/frontend/src/components/MusicSpectrumBackdrop.vue`
- Modify: `tests/test_music_page_lifecycle.py`

**Interfaces:**
- Consumes: `MusicPlaybackBackdrop` contract from Task 1
- Produces: unchanged MusicPage player and error behavior

- [ ] Update the test to require `MusicPlaybackBackdrop` and reject Butterchurn, spectrum, and audio-element bridge references.
- [ ] Run the focused test and verify it fails on the old MusicPage import.
- [ ] Replace the component import/template reference and delete the obsolete component.
- [ ] Run all lifecycle tests, Ruff, and the Vite production build.

### Task 3: Package and measure

**Files:**
- Modify: generated ignored frontend `dist/` and Tauri `target/` artifacts only

**Interfaces:**
- Consumes: verified frontend production build
- Produces: installed `/Applications/乐兔.app`

- [ ] Build the signed Tauri app using the existing generated frontend output.
- [ ] Install the bundle, launch it, and play the current track.
- [ ] Verify no visualizer error appears and sample WebContent/GPU CPU for eight seconds.
- [ ] Commit only the scoped source, test, and documentation files.
