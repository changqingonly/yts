# Lightweight Music Spectrum Design

## Goal

Replace the Butterchurn navigation background with a static playback-state treatment so music playback no longer drives sustained WebContent CPU usage above 20%.

## Design

`MusicPlaybackBackdrop.vue` renders three fixed colored bars and changes opacity only when the existing `playing` prop changes. It owns no audio graph, canvas, timer, animation frame, or visibility listener. The audio element therefore returns to native WebKit playback without a `MediaElementAudioSourceNode`.

The component never imports Butterchurn, loads presets, creates WebGL or Canvas contexts, or silently falls back. `MusicPage.vue` passes only the playback boolean and removes the audio-element bridge and visualizer error callback. The obsolete Butterchurn and spectrum components are deleted after the new component and tests pass.

## Verification

Source-contract tests verify the static playback contract and absence of audio analysis, Canvas, timers, animation frames, WebGL, and Butterchurn imports. The frontend production build must omit Butterchurn chunks. The installed Tauri app must play audio, and an eight-second CPU sample must be materially lower than the measured Butterchurn range of 23%-27% WebContent CPU.
