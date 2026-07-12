# Music Full-Spectrum Visualizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `/music` Butterchurn backdrop into the approved B full-spectrum primary visual while preserving explicit renderer failures and readable playback controls.

**Architecture:** Keep the existing `MusicPage -> YtsAudioPlayer -> MusicButterchurnBackdrop` audio and playback control flow unchanged. Add one selector-scoped source contract test, then change only the backdrop's normal-motion CSS composition; retain the reduced-motion rule and all WebGL lifecycle code.

**Tech Stack:** Vue 3 SFC, Butterchurn 2.6.7, CSS filters/gradients, pytest source-contract tests, Vite 8.

---

## Execution Context

Execute in the current worktree. `MusicButterchurnBackdrop.vue` is currently untracked and `test_music_page_lifecycle.py` already contains user changes that are not in `HEAD`; a new worktree would omit the implementation context. Preserve every unrelated working-tree change.

Do not stage or commit the implementation files. Staging either whole file would absorb pre-existing user work. The design and plan documents are independently trackable; implementation changes must remain as a reviewed working-tree diff unless the user later requests a commit strategy.

## File Map

- Modify `tests/test_music_page_lifecycle.py`: add a small selector-scoped CSS declaration parser and the failing full-spectrum composition contract.
- Modify `desktop/frontend/src/components/MusicButterchurnBackdrop.vue`: update only active opacity, overlay gradients, and canvas filter.
- Do not modify `desktop/frontend/src/pages/MusicPage.vue`, `desktop/frontend/src/components/YtsAudioPlayer.vue`, stores, or Web Audio lifecycle code.

### Task 1: Add The Failing Visual Composition Contract

**Files:**
- Modify: `tests/test_music_page_lifecycle.py:9-14`
- Test: `tests/test_music_page_lifecycle.py:194`

- [ ] **Step 1: Add a selector-scoped declaration helper**

Add this helper after `read_frontend_file`:

```python
def css_declarations(style: str, selector: str) -> dict[str, str]:
    rule = style.split(f"{selector} {{", 1)[1].split("}", 1)[0]
    declarations: dict[str, str] = {}
    for declaration in rule.split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        declarations[name.strip()] = " ".join(value.split())
    return declarations
```

This parser is intentionally limited to the three flat component rules under test. It does not scan the whole repository or interpret unrelated CSS.

- [ ] **Step 2: Add the failing full-spectrum test**

Append this test after `test_butterchurn_backdrop_uses_explicit_webgl_lifecycle_without_fallback`:

```python
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
```

- [ ] **Step 3: Run the focused test and verify RED**

Run from the repository root:

```bash
.venv/bin/pytest \
  tests/test_music_page_lifecycle.py::test_butterchurn_backdrop_uses_full_spectrum_composition_without_hue_rotation \
  -q
```

Expected: one failure at `assert active["opacity"] == "0.9"`, showing current value `0.3`. A collection error, parser error, or unrelated failure is not an acceptable RED state; fix the test setup and rerun until it fails for the visual mismatch.

### Task 2: Apply The Approved B Composition

**Files:**
- Modify: `desktop/frontend/src/components/MusicButterchurnBackdrop.vue:197-217`
- Test: `tests/test_music_page_lifecycle.py`

- [ ] **Step 1: Update the normal-motion CSS only**

Replace the three normal-motion rules with these exact declarations, leaving the base hidden state and reduced-motion media query unchanged:

```css
.music-butterchurn-backdrop.active {
  opacity: 0.9;
}

.music-butterchurn-backdrop::after {
  background:
    radial-gradient(circle at 50% 42%, transparent 0 64%, rgba(4, 11, 21, 0.24) 100%),
    linear-gradient(180deg, rgba(4, 11, 21, 0.02), rgba(4, 11, 21, 0.18));
  content: "";
  inset: 0;
  pointer-events: none;
  position: absolute;
}

.music-butterchurn-backdrop canvas {
  display: block;
  filter: saturate(1.5) contrast(1.08);
  height: 100%;
  transform: scale(1.04);
  width: 100%;
}
```

Do not change `PRESET_NAME`, `WEBGL_OPTIONS`, `ensureVisualizer`, the render loop, error emission, or teardown.

- [ ] **Step 2: Run the focused test and verify GREEN**

```bash
.venv/bin/pytest \
  tests/test_music_page_lifecycle.py::test_butterchurn_backdrop_uses_full_spectrum_composition_without_hue_rotation \
  -q
```

Expected: `1 passed` with no warnings or errors.

- [ ] **Step 3: Inspect the scoped diff**

```bash
git diff -- \
  tests/test_music_page_lifecycle.py \
  desktop/frontend/src/components/MusicButterchurnBackdrop.vue
```

Expected: the new test/helper and the approved CSS values only. Because the files already contain user work, distinguish the new hunks from pre-existing changes and do not revert or stage the latter.

### Task 3: Run Automated Regression Verification

**Files:**
- Verify: `tests/test_music_page_lifecycle.py`
- Verify: `tests/test_frontend_creator_os_layout.py`
- Verify: `desktop/frontend/package.json`

- [ ] **Step 1: Run the complete music lifecycle tests**

```bash
.venv/bin/pytest tests/test_music_page_lifecycle.py -q
```

Expected: all tests in the file pass, including the WebGL lifecycle/no-fallback contract and the new composition contract.

- [ ] **Step 2: Run related frontend layout tests**

```bash
.venv/bin/pytest tests/test_frontend_creator_os_layout.py -q
```

Expected: all tests pass. Any failure must be reported with its exact assertion; do not weaken unrelated layout contracts to make this change pass.

- [ ] **Step 3: Build the frontend production bundle**

Run from `desktop/frontend` with the repository-provided Node runtime:

```bash
PATH=/Users/bytedance/Documents/projects/yts/.tools/node/bin:$PATH npm run build
```

Expected: Vite exits `0` and emits a production bundle without unresolved imports or CSS compilation errors.

### Task 4: Verify The Real Music Experience

**Files:**
- Inspect: `http://127.0.0.1:1420/music`
- Temporary evidence only: `/tmp/yts-music-spectrum-*.png`

- [ ] **Step 1: Inspect the playing desktop state**

Use the in-app browser control skill to claim or open `http://127.0.0.1:1420/music`. Set a desktop viewport near `1440x900`, start an available track if it is paused, and verify these authoritative DOM signals:

```text
.music-butterchurn-backdrop has class "active"
computed backdrop opacity is "0.9"
computed canvas filter is "saturate(1.5) contrast(1.08)"
canvas CSS width and height are both greater than zero
audio.paused is false
```

Capture the visualizer region twice at least 400 ms apart. The two canvas-region PNGs must not be byte-identical, and both must visibly contain multiple hue families rather than a cyan-only field. Save one desktop screenshot to `/tmp/yts-music-spectrum-desktop.png` and inspect it before proceeding.

- [ ] **Step 2: Verify controls on bright frames**

Inspect a frame containing bright yellow/green or magenta highlights. Confirm the timeline, current-time label, track title, previous/play-next controls, volume controls, and loop mode remain readable without adding another global dark overlay.

If controls are unreadable, stop and report the failed acceptance criterion. Do not silently depart from the approved CSS values; any additional treatment requires a design revision.

- [ ] **Step 3: Inspect the narrow mobile state**

Set a viewport near `390x844`, reload the built page, and capture `/tmp/yts-music-spectrum-mobile.png`. Confirm the canvas remains nonblank, no text or controls overlap, no horizontal overflow appears, and the full-spectrum animation is still visually dominant.

- [ ] **Step 4: Verify pause and explicit failure behavior**

Pause playback and confirm the backdrop loses `active` and transitions to `opacity: 0`. Do not simulate a WebGL failure by patching runtime state; the unchanged lifecycle/no-fallback source contract and passing test provide the failure-path evidence for this CSS-only change.

### Task 5: Final Review And Handoff

**Files:**
- Review: `tests/test_music_page_lifecycle.py`
- Review: `desktop/frontend/src/components/MusicButterchurnBackdrop.vue`

- [ ] **Step 1: Run whitespace and status checks**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. Status still includes unrelated pre-existing user changes; report them without reverting them.

- [ ] **Step 2: Reconcile the implementation against the design**

Verify each exact value from `docs/superpowers/specs/2026-07-12-music-full-spectrum-visualizer-design.md` appears in the selector-scoped test and component CSS. Confirm no production source outside `MusicButterchurnBackdrop.vue` was changed for this implementation.

- [ ] **Step 3: Do not commit the implementation files**

Leave the verified implementation in the working tree. Report the targeted/full test counts, build result, desktop/mobile visual findings, evidence screenshot paths, and the two files changed by this task.
