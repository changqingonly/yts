# Volume Track Thickness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the audio player's volume track at 2px while preserving its 12px thumb and existing behavior.

**Architecture:** Keep the native range input and its current event flow. Change only the WebKit and Firefox track pseudo-element heights in the existing audio player component, with source-level assertions and a frontend build guarding the result.

**Tech Stack:** Vue 3 single-file component, CSS range pseudo-elements, Vite, pytest

## Global Constraints

- The volume track height must be 2px in WebKit and Firefox.
- The volume thumb must remain 12px in WebKit and Firefox.
- Volume behavior, colors, focus treatment, and responsive visibility must remain unchanged.

---

### Task 1: Thin the volume track

**Files:**
- Modify: `desktop/frontend/src/components/YtsAudioPlayer.vue`
- Modify: `tests/test_music_page_lifecycle.py`

**Interfaces:**
- Consumes: Existing `.volume-range` native range input and `handleVolumeInput(event)` behavior.
- Produces: A 2px visual track with the existing 12px thumb on WebKit and Firefox.

- [ ] **Step 1: Add a failing source-level style test**

Add a test that reads `YtsAudioPlayer.vue`, extracts the WebKit and Firefox volume track rule bodies, and asserts that each contains `height: 2px`; also extract both thumb rule bodies and assert that each still contains `height: 12px` and `width: 12px`.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `./.venv/bin/pytest tests/test_music_page_lifecycle.py -q`

Expected: FAIL because both volume track rules currently contain `height: 4px`.

- [ ] **Step 3: Apply the minimal CSS change**

In `desktop/frontend/src/components/YtsAudioPlayer.vue`, change only these declarations:

```css
.volume-range::-webkit-slider-runnable-track {
  height: 2px;
}

.volume-range::-moz-range-track {
  height: 2px;
}
```

Keep both thumb blocks at `height: 12px` and `width: 12px`.

- [ ] **Step 4: Run focused and build verification**

Run: `./.venv/bin/pytest tests/test_music_page_lifecycle.py -q`

Expected: PASS.

Run: `npm run build`

Working directory: `desktop/frontend`

Expected: Vite build exits with status 0.

- [ ] **Step 5: Visually verify the desktop player**

Run the existing frontend, open the music page at desktop width, and confirm the volume line is visibly thinner while its round thumb stays the same size.

- [ ] **Step 6: Commit the implementation**

```bash
git add desktop/frontend/src/components/YtsAudioPlayer.vue tests/test_music_page_lifecycle.py
git commit -m "fix: thin volume track"
```
