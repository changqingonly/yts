# Music Local Startup Readiness Design

## Goal

Prevent the music page from reporting a playlist failure while the restored local target is still starting.

## Control Flow

- Music page mount starts or joins `environment.checkHealth(target)` before requesting playlist data.
- Environment switches use the same readiness-gated playlist refresh path.
- While health is `checking`, the existing empty player and yellow target status dot remain visible; no error banner is shown.
- When health becomes `online`, the page immediately loads the playlist.
- When the 30-second local health deadline returns `offline`, the page shows an explicit target connection failure.
- A readiness result for an old target is ignored if the user switched targets while waiting.

## Error Handling

- Startup connection errors remain owned by the health-check loop until it reaches `online` or `offline`.
- Playlist request errors after `online` continue to use the existing detailed request error banner.
- No retry delay, fallback endpoint, swallowed terminal failure, or silent degradation is added.

## Verification

- Add a source-level lifecycle test proving mount and target switch await health before playlist refresh.
- Run the focused test red, then green after implementation.
- Run the full music lifecycle test file and frontend build.
