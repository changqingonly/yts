# Remove Settings Header Profile Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant profile link from the settings header while retaining the account-section profile link.

**Architecture:** Make a template and scoped-CSS deletion in the existing settings page. Protect the information architecture with a source-level layout test.

**Tech Stack:** Vue 3 SFC, Vue Router, pytest, Vite

## Global Constraints

- Preserve the account-section profile link and `/profile/setup` route.
- Do not change settings navigation or responsive layout beyond removing header-link-only CSS.

---

### Task 1: Remove the duplicate header profile link

**Files:**
- Modify: `tests/test_frontend_creator_os_layout.py`
- Modify: `desktop/frontend/src/pages/SettingsPage.vue`

- [ ] Add a failing source-level test requiring `.header-profile-link` to be absent and `.account-link` to remain.
- [ ] Run the focused test and confirm failure against the current header link.
- [ ] Delete the header `RouterLink` and all `.header-profile-link` style rules.
- [ ] Run the full layout tests and `npm run build` from `desktop/frontend`.
