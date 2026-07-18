# Settings Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the settings page as a restrained dark interface with compact in-page navigation for general, usage, and account settings.

**Architecture:** Keep all state and business control flow inside the existing `SettingsPage.vue`; add only a local active-section state and computed presentation helpers. Preserve the existing credit service calls, local-storage model preference, profile route, and logout action while replacing the template and scoped styles.

**Tech Stack:** Vue 3 Composition API, Vue Router, Pinia, Lucide Vue, scoped CSS, pytest source-contract tests, Vite.

## Global Constraints

- Keep the existing dark theme and the tokens defined in `desktop/frontend/src/styles/base.css`.
- Do not add a theme switch, backend endpoint, child route, or global sidebar change.
- Errors from loading settings or logging out must be displayed explicitly; do not add fallback behavior or silent degradation.
- Use in-page navigation with exactly three groups: `general`, `usage`, and `account`.
- Use spacing and dividers instead of nested cards; border radius must not exceed 8px.
- On narrow screens, convert the left navigation into horizontal tabs and keep content in one column.

---

### Task 1: Settings Page Structure, Behavior, and Styling

**Files:**
- Modify: `tests/test_frontend_creator_os_layout.py`
- Modify: `desktop/frontend/src/pages/SettingsPage.vue`

**Interfaces:**
- Consumes: `fetchCreditBalance(): Promise<object>`, `fetchCreditLedger(): Promise<Array>`, `fetchDailyUsage(): Promise<object>`, `auth.logoutAction(): Promise<void>`, Vue Router `push()`.
- Produces: local `activeSection: Ref<"general" | "usage" | "account">`, `settingsSections` navigation metadata, `usageRows` computed presentation data, and a responsive settings-page template.

- [ ] **Step 1: Add a failing source-contract test**

Append this test to `tests/test_frontend_creator_os_layout.py`:

```python
def test_settings_page_uses_compact_in_page_navigation_and_preserves_control_flow() -> None:
    settings = read_source("pages/SettingsPage.vue")
    template = settings.split("<template>", 1)[1].split("</template>", 1)[0]

    for token in [
        'const activeSection = ref("general");',
        'key: "general"',
        'key: "usage"',
        'key: "account"',
        'aria-label="设置分类"',
        ':aria-current="activeSection === item.key ? \'page\' : undefined"',
        'role="alert"',
        'class="settings-content"',
        'class="usage-progress"',
        '@change="saveModelPreference"',
        'to="/profile/setup"',
        '@click="logout"',
    ]:
        assert token in settings

    assert 'v-if="activeSection === \'general\'"' in template
    assert 'v-else-if="activeSection === \'usage\'"' in template
    assert 'v-else' in template
    assert "grid-template-columns: 168px minmax(0, 1fr);" in settings
    assert "grid-template-columns: 1fr;" in settings
    assert "linear-gradient" not in settings
    assert "border-radius: 999px" not in settings
    assert "fetchCreditBalance()" in settings
    assert "fetchCreditLedger()" in settings
    assert "fetchDailyUsage()" in settings
    assert "await auth.logoutAction();" in settings
    assert 'router.push({ name: "login" });' in settings
```

- [ ] **Step 2: Run the new test and confirm the expected failure**

Run:

```bash
uv run pytest tests/test_frontend_creator_os_layout.py::test_settings_page_uses_compact_in_page_navigation_and_preserves_control_flow -v
```

Expected: FAIL because `SettingsPage.vue` does not yet define `activeSection` or the settings navigation.

- [ ] **Step 3: Implement the local presentation state**

In `SettingsPage.vue`, retain the existing request and logout functions. Add `computed` to the Vue import, define the three navigation items, initialize `activeSection` to `general`, and derive `usageRows` from `dailyUsage`. Each usage row must contain `key`, `label`, `used`, `limit`, and a bounded percentage used only for CSS width. Do not replace missing API values with fabricated API results; the displayed zero values remain presentation placeholders while loading, and request errors remain visible through `error`.

```js
const activeSection = ref("general");
const settingsSections = [
  { key: "general", label: "通用", icon: SlidersHorizontal },
  { key: "usage", label: "用量", icon: ChartNoAxesColumnIncreasing },
  { key: "account", label: "账户", icon: UserRound },
];
const usageRows = computed(() => [
  { key: "lyrics", label: "歌词生成", used: dailyUsage.value?.lyrics?.used ?? 0, limit: dailyUsage.value?.lyrics?.limit ?? 100 },
  { key: "images", label: "图片生成", used: dailyUsage.value?.images?.used ?? 0, limit: dailyUsage.value?.images?.limit ?? 100 },
  { key: "audio_effects", label: "音频特效", used: dailyUsage.value?.audio_effects?.used ?? 0, limit: dailyUsage.value?.audio_effects?.limit ?? 100 },
].map((row) => ({ ...row, percent: Math.min(100, Math.max(0, (row.used / row.limit) * 100)) })));
```

- [ ] **Step 4: Replace the template with the approved information architecture**

Build a constrained page header followed by a two-column `.settings-shell`. Use real buttons for the secondary navigation, set `aria-current` on the active item, and conditionally render exactly one content section. Keep the model `<select>`, credit figures, empty ledger state, profile `RouterLink`, explicit error alert, and logout disabled/loading behavior.

- [ ] **Step 5: Implement restrained dark responsive styles**

Replace the old panel-grid CSS with scoped styles using existing theme variables. The desktop shell must use `grid-template-columns: 168px minmax(0, 1fr)`. At `max-width: 720px`, switch to `grid-template-columns: 1fr`, make navigation horizontal, and keep all settings rows responsive. Add `:focus-visible` rules, stable control heights, divider-based grouping, and no gradients or decorative effects.

- [ ] **Step 6: Run the focused test and full layout contract suite**

Run:

```bash
uv run pytest tests/test_frontend_creator_os_layout.py::test_settings_page_uses_compact_in_page_navigation_and_preserves_control_flow -v
uv run pytest tests/test_frontend_creator_os_layout.py -v
```

Expected: both commands PASS.

- [ ] **Step 7: Commit the implementation**

```bash
git add desktop/frontend/src/pages/SettingsPage.vue tests/test_frontend_creator_os_layout.py
git commit -m "feat: redesign settings page"
```

### Task 2: Build and Visual Verification

**Files:**
- Verify: `desktop/frontend/src/pages/SettingsPage.vue`

**Interfaces:**
- Consumes: completed settings-page implementation from Task 1 and the existing authenticated application shell.
- Produces: verified production bundle and desktop/mobile visual evidence.

- [ ] **Step 1: Build the frontend production bundle**

Run:

```bash
npm run build
```

from `desktop/frontend`.

Expected: Vite exits with code 0 and produces the production bundle.

- [ ] **Step 2: Start the existing development server**

Run:

```bash
npm run dev -- --host 127.0.0.1
```

Expected: Vite prints a reachable local URL. If its default port is occupied, use the next available port shown by Vite.

- [ ] **Step 3: Verify desktop and narrow viewports in the browser**

Open `/settings` in the running application. At approximately `1440x900`, verify the 168px secondary navigation, constrained content width, selected navigation state, readable usage values, and separated account danger area. At approximately `390x844`, verify horizontal tabs, one-column content, wrapped text, stable controls, and no overlap or horizontal overflow.

- [ ] **Step 4: Exercise all three groups and failure-visible controls**

Switch among 通用, 用量, and 账户. Confirm section switching does not reload the page, the model select remains operable, the profile link targets `/profile/setup`, and the logout button visibly enters its disabled state. Confirm any backend failure appears in the alert rather than being hidden.

- [ ] **Step 5: Review screenshots and make only scoped polish corrections**

Capture desktop and narrow screenshots. Check contrast, hierarchy, spacing, focus states, progress-bar framing, text containment, and absence of nested cards. If a defect is visible, correct only `SettingsPage.vue`, rerun the focused pytest command and `npm run build`, then capture the affected viewport again.
