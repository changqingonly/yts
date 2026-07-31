# Dark macOS Title Bar Design

## Goal

Make the native macOS title bar match the application's dark interface.

## Behavior

- Set the Tauri main window theme to `dark`.
- Keep native window decorations, traffic-light controls, title, dragging, and double-click behavior unchanged.
- Do not replace the native title bar with frontend HTML.

## Verification

- Parse `tauri.conf.json` and assert the main window theme is `dark`.
- Validate the Tauri configuration through the installed CLI.
- Run `cargo check` for the Tauri crate.
