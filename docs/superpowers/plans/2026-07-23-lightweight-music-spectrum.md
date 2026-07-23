# Lightweight Music Spectrum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Butterchurn with a low-cost audio-reactive canvas in the music navigation item.

**Architecture:** A Vue component builds a single Web Audio analyser graph around the existing audio element and draws twelve bars into a 2D canvas at 12 FPS. MusicPage retains its public wiring while all Butterchurn runtime code is removed.

**Tech Stack:** Vue 3, Web Audio API, Canvas 2D, pytest source-contract tests, Vite, Tauri 2.

## Global Constraints

- Preserve native audio playback behavior and existing MusicPage event wiring.
- Stop visual rendering when paused or hidden.
- Fail explicitly on analyser or canvas errors; no fallback or silent degradation.
- Preserve unrelated dirty-worktree changes.

---

### Task 1: Lightweight spectrum component

**Files:**
- Create: `desktop/frontend/src/components/MusicSpectrumBackdrop.vue`
- Modify: `tests/test_music_page_lifecycle.py`

**Interfaces:**
- Consumes: `audioElement: HTMLAudioElement | null`, `playing: boolean`
- Produces: `visualizer-error(message: string)`

- [ ] Write a failing source-contract test requiring `AnalyserNode`, Canvas 2D, twelve bars, 12 FPS, DPR 1.25, and visibility cleanup.
- [ ] Run `pytest tests/test_music_page_lifecycle.py -q` and verify failure because the component does not exist.
- [ ] Implement the component with one explicit audio graph and one animation-frame loop.
- [ ] Run the focused lifecycle tests and Ruff until they pass.

### Task 2: Replace Butterchurn wiring

**Files:**
- Modify: `desktop/frontend/src/pages/MusicPage.vue`
- Delete: `desktop/frontend/src/components/MusicButterchurnBackdrop.vue`
- Modify: `tests/test_music_page_lifecycle.py`

**Interfaces:**
- Consumes: `MusicSpectrumBackdrop` contract from Task 1
- Produces: unchanged MusicPage player and error behavior

- [ ] Update the test to require `MusicSpectrumBackdrop` and reject Butterchurn imports and component references.
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
