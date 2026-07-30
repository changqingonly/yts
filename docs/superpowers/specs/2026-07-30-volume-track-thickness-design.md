# Volume Track Thickness Design

## Goal

Reduce the audio player's volume track thickness from 4px to 2px while keeping the 12px thumb unchanged.

## Scope

- Update the WebKit volume range track height to 2px.
- Update the Firefox volume range track height to 2px.
- Keep the thumb size, colors, focus treatment, input behavior, and responsive visibility unchanged.

## Verification

- Build the frontend successfully.
- Confirm both volume track declarations use 2px and both thumb declarations remain 12px.
- Visually verify the player at desktop width.
