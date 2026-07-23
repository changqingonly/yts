# Lightweight Music Spectrum Design

## Goal

Replace the Butterchurn navigation background with a lightweight audio-reactive canvas so music playback no longer drives sustained WebContent CPU usage above 20%.

## Design

`MusicSpectrumBackdrop.vue` owns one `AudioContext`, one `MediaElementAudioSourceNode`, and one `AnalyserNode`. The media source connects through the analyser to the audio destination, preserving audible playback while exposing frequency data. A 2D canvas renders twelve mirrored spectrum bars at 4 FPS using a DPR cap of 1.25 and a timer that does not wake on every display refresh. Rendering stops while playback is paused or the document is hidden; audio graph failures are emitted explicitly through `visualizer-error`.

The component never imports Butterchurn, loads presets, creates WebGL contexts, or silently falls back. `MusicPage.vue` keeps the existing prop and event contract but imports the new component. The obsolete Butterchurn component is deleted after the new component and tests pass.

## Verification

Source-contract tests verify the analyser graph, 2D canvas, 12 FPS throttle, DPR cap, visibility lifecycle, explicit error propagation, and absence of Butterchurn imports. The frontend production build must omit Butterchurn chunks. The installed Tauri app must play audio without a visualizer error, and an eight-second CPU sample must be materially lower than the measured Butterchurn range of 23%-27% WebContent CPU.
