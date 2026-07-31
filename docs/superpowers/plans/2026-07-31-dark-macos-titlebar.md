# Dark macOS Title Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure the native Tauri main window to use macOS dark appearance.

**Architecture:** Use Tauri's supported `WindowConfig.theme` field. This keeps native window behavior intact and avoids a custom title-bar implementation.

**Tech Stack:** Tauri 2, JSON, pytest, Rust

## Global Constraints

- Preserve native macOS window decorations and traffic-light controls.
- Do not add custom frontend title-bar markup.

---

### Task 1: Set the native window theme

**Files:**
- Modify: `tests/test_frontend_creator_os_layout.py`
- Modify: `desktop/src-tauri/tauri.conf.json`

- [ ] Add a failing structured JSON assertion for `app.windows[0].theme == "dark"`.
- [ ] Run the focused test and confirm it fails because the field is absent.
- [ ] Add `"theme": "dark"` to the main window configuration.
- [ ] Run the focused test, Tauri configuration validation, and `cargo check`.
