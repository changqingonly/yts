# Butterchurn Performance Design

## Goal

Reduce Butterchurn CPU and graphics-process usage without changing audio playback.

## Design

The visualizer will render at no more than 30 frames per second, cap its backing-canvas pixel ratio at 1.25, and stop its animation loop while the document is hidden. Audio playback and the `MediaElementAudioSourceNode` remain active; only visual rendering pauses. When visibility returns during playback, rendering resumes through the existing visualizer instance.

The component will keep one animation-frame request at a time. Frame throttling is timestamp-based, and stopping the loop resets its timestamp so resumed rendering draws immediately. WebGL, AudioContext, preset, and renderer failures remain explicit through the existing `visualizer-error` event.

## Testing

A focused source-contract test will verify the 30 FPS interval, 1.25 pixel-ratio cap, timestamp throttling, visibility gate, and visibility listener lifecycle. Existing Butterchurn lifecycle tests and the frontend build must continue to pass.
