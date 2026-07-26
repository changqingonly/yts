# Playback Timeline Contrast Design

## Problem

The music player's native `input[type="range"]` only sets `accent-color`. On macOS WebView, the remaining track and thumb colors are supplied by the dark system color scheme, so they become difficult to distinguish from the playback backdrop.

## Design

Keep the native range input and its existing event-driven playback flow. Render its WebKit and Firefox track, progress, and thumb pseudo-elements explicitly:

- the unplayed track uses a translucent near-white fill plus a dark outline;
- the played segment uses the existing brand cyan;
- the thumb uses a near-white center, cyan border, and dark outer shadow;
- focus-visible adds a cyan focus ring;
- disabled state remains visibly disabled without losing the track outline.

The component's existing `--timeline-progress` custom property remains the sole progress source. WebKit uses it in a track background gradient; Firefox uses its native progress pseudo-element. No background sampling, JavaScript color adaptation, or fallback behavior is introduced.

## Verification

Add a source-contract regression test for the explicit cross-engine range styling and progress binding. Run the focused lifecycle tests, the full frontend source-contract test module, and the frontend production build. Verify the rendered player on both dark and light test backdrops at desktop and narrow viewport widths.

