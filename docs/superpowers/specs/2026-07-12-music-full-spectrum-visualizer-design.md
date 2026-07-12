# Music Full-Spectrum Visualizer Design

## Goal

Make the Butterchurn background on `/music` a full-spectrum primary visual. Color changes must be immediately visible while the timeline, track metadata, and transport controls remain readable.

## Scope

The change is limited to the final CSS composition in `MusicButterchurnBackdrop.vue`. The selected Butterchurn preset, Web Audio graph, playback state flow, renderer lifecycle, and player layout remain unchanged.

`MusicPage.vue` continues to pass the mounted audio element and `player.isPlaying` to the backdrop. `MusicButterchurnBackdrop.vue` continues to create the visualizer, connect audio, load the named preset, render only while playing, and destroy resources on audio-element changes or unmount.

## Visual Composition

Use the approved B, full-spectrum treatment with these exact normal-motion values:

- `.music-butterchurn-backdrop.active` uses `opacity: 0.9`.
- The canvas uses `filter: saturate(1.5) contrast(1.08)`.
- The canvas filter contains no hue rotation. Preset colors remain distinct rather than being shifted into the cyan range.
- The radial overlay stays transparent through 64% of the visual field and reaches only `rgba(4, 11, 21, 0.24)` at the outer edge.
- The vertical overlay runs from `rgba(4, 11, 21, 0.02)` at the top to `rgba(4, 11, 21, 0.18)` at the bottom.
- Existing canvas sizing and the `scale(1.04)` edge coverage remain unchanged.

The bottom overlay is deliberately narrow in strength. It supports control readability without turning the visualizer back into an ambient dark texture. Existing button backgrounds, text colors, and z-index layering remain unchanged.

## Reduced Motion And Failures

The current `prefers-reduced-motion: reduce` rule remains authoritative and keeps the active backdrop at `opacity: 0`.

Initialization failures remain explicit. Missing canvas, missing preset, unavailable WebGL2, AudioContext failures, and Butterchurn errors continue through the existing `visualizer-error` event into the page error message. No static image, alternate renderer, preset substitution, or silent fallback is added.

## Test Design

Add a focused test to `tests/test_music_page_lifecycle.py` after the existing Butterchurn lifecycle test. The test must:

1. Read the component's scoped style and isolate normal CSS before the media query.
2. Parse declarations from the `.music-butterchurn-backdrop.active`, `.music-butterchurn-backdrop::after`, and `.music-butterchurn-backdrop canvas` rules.
3. Assert active opacity is exactly `0.9`.
4. Assert the canvas filter functions are exactly `saturate(1.5)` and `contrast(1.08)`, which also proves hue rotation is absent from that rule.
5. Assert the normalized overlay background exactly matches the approved radial and vertical gradients.

The test is written and run before the component change. It must fail against the current ambient treatment for the expected visual-parameter mismatch.

## Verification

After the targeted test passes:

1. Run the complete music lifecycle test file.
2. Run the related frontend layout tests to catch layering or player-layout regressions.
3. Build the frontend production bundle.
4. Inspect the real `/music` page while audio is playing at desktop and narrow mobile viewports.
5. Confirm the canvas is nonblank, colors change over time, the result matches the approved full-spectrum direction, and the timeline and transport controls remain readable.

No production source outside `MusicButterchurnBackdrop.vue` should change for this implementation.
