# Profile Settings Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the profile editor into the dark settings module with real secondary navigation, explicit loading/upload errors, and responsive form layout.

**Architecture:** Keep profile data operations in `ProfileSetupPage.vue` and reuse the existing profile service. Extend `SettingsPage.vue` only to synchronize its local active section with a strictly validated `section` query parameter.

**Tech Stack:** Vue 3 Composition API, Vue Router, Pinia, Lucide Vue, scoped CSS, pytest source-contract tests, Vite.

## Global Constraints

- Preserve existing profile API payloads and authentication-store synchronization.
- Do not add backend endpoints, global navigation changes, theme switching, fallback behavior, or silent degradation.
- Invalid `section` query values must produce an explicit visible error.
- Use existing dark theme tokens, no gradients, no nested cards, and no radius above 8px.
- Desktop navigation width is 168px; narrow screens use horizontal secondary navigation and single-column fields.

---

### Task 1: Add Profile Settings and Query Navigation Contracts

**Files:**
- Modify: `tests/test_frontend_creator_os_layout.py`

**Interfaces:**
- Consumes: Vue page source files.
- Produces: source contracts for strict query parsing, integrated navigation, form association, and explicit profile errors.

- [ ] Add a test asserting `SettingsPage.vue` imports `useRoute`, validates `route.query.section` against `general`, `usage`, and `account`, watches query changes, and renders invalid values through `role="alert"`.
- [ ] Add a test asserting `ProfileSetupPage.vue` links to `/settings` and `/settings?section=usage`, marks account current, uses `form="profile-form"`, exposes loading/upload state, and catches load/read/upload/save errors.
- [ ] Run both focused tests and confirm they fail because the new contracts are absent.

Run:

```bash
uv run pytest tests/test_frontend_creator_os_layout.py -k "profile_settings or settings_page_reads_section_query" -v
```

Expected: FAIL on missing query synchronization and integrated profile layout.

### Task 2: Implement Strict Settings Query Synchronization

**Files:**
- Modify: `desktop/frontend/src/pages/SettingsPage.vue`

**Interfaces:**
- Consumes: `route.query.section`.
- Produces: `sectionFromQuery(value): "general" | "usage" | "account"`, synchronized `activeSection`, and explicit query error.

- [ ] Import `watch`, `useRoute`, and initialize the route instance.
- [ ] Implement `sectionFromQuery`: return `general` only when the parameter is absent; return recognized string values; throw `Error("未知设置分类: <value>")` for arrays or unsupported values.
- [ ] Watch `route.query.section` immediately, update `activeSection` on success, and set the existing page error on failure without changing the current section.
- [ ] Run the focused settings-query test and confirm it passes.

### Task 3: Rebuild the Profile Editor

**Files:**
- Modify: `desktop/frontend/src/pages/ProfileSetupPage.vue`

**Interfaces:**
- Consumes: existing `fetchProfile`, `updateProfile`, `uploadAvatar`, and auth store.
- Produces: `profile-form`, `profileLoading`, `avatarUploading`, explicit alert/status state, and integrated settings navigation.

- [ ] Add explicit `profileLoading` and `avatarUploading` refs. Wrap `loadProfile` in try/catch/finally; wrap the complete file-read/upload sequence in try/catch/finally.
- [ ] Keep `saveProfile` payload and auth synchronization unchanged; disable saving during load, upload, or save.
- [ ] Replace the template with shared settings page structure, real navigation links, a header save button associated to `profile-form`, avatar section, basic-information grid, and biography section.
- [ ] Replace scoped styles with the approved dark divider-based design and responsive breakpoints at 720px and 460px.
- [ ] Run the focused profile test, then the complete layout contract suite.

Run:

```bash
uv run pytest tests/test_frontend_creator_os_layout.py -q
```

Expected: all layout contract tests PASS.

### Task 4: Build and Verify

**Files:**
- Verify: `desktop/frontend/src/pages/ProfileSetupPage.vue`
- Verify: `desktop/frontend/src/pages/SettingsPage.vue`

**Interfaces:**
- Consumes: completed implementation.
- Produces: production build and verification report.

- [ ] Run `npm run build` from `desktop/frontend`; expect exit code 0.
- [ ] Run `git diff --check`; expect exit code 0.
- [ ] With a real authenticated local session, inspect `/profile/setup`, `/settings`, and `/settings?section=usage` at desktop and narrow viewports. If no authenticated session exists, report that limitation and do not bypass authentication.
