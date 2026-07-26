# Music Navigation Spinning Disc Design

## Goal

Make the music navigation tile visibly animated while audio is playing, using the selected looping-record direction from the visual comparison.

## Behavior

`MusicPlaybackBackdrop` continues to consume only its existing `playing` boolean. When `playing` is true, the backdrop becomes visible and a cyan, pink, and green record rotates continuously. When playback pauses, the backdrop hides and the animation stops because the element is no longer active.

The visible "音乐" label remains owned by `AppShell`; the backdrop stays decorative and `aria-hidden`.

## Visual Design

The record is drawn with CSS using a conic gradient, a light outer rim, a dark center hole, and a short highlight groove. It fits within the existing navigation tile and does not alter the tile's dimensions or layout.

## Performance And Accessibility

The animation is CSS-only. It must not use `AudioContext`, audio analysers, canvas, WebGL, timers, or `requestAnimationFrame`. Under `prefers-reduced-motion: reduce`, the record remains visible in its active state but does not rotate.

## Verification

Update the lifecycle source-contract test to require the record markup, active-state animation, CSS keyframes, and reduced-motion rule while preserving all existing prohibitions on continuous JavaScript or audio-analysis work. Run the focused test, the full lifecycle module, the frontend build, and desktop/mobile visual checks for playing and paused states.

