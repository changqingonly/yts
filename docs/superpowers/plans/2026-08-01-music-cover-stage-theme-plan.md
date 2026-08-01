# Music Cover Stage And Theme Background Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将音乐页改造成参考截图的方形封面主舞台，并在封面生成完成时计算、持久化主题色供前端背景融合使用。

**Architecture:** 主题色属于封面产物元数据，由 `music_covers` 生成 worker 在 PNG 校验后计算并写入 `MusicCoverJob`；API 状态响应携带主题色，前端仅消费该值。播放器主舞台拆为左侧方形封面、右侧歌曲信息/歌词空状态和底部原有播放控制，播放事件契约保持不变。

**Tech Stack:** Python 3、FastAPI、SQLAlchemy async、SQLite migrations/bootstrap、imageio-ffmpeg、Vue 3、CSS、pytest。

## Global Constraints

- 封面必须保持 `aspect-ratio: 1 / 1`，不得用黑胶中心圆形裁切作为主要展示。
- 主题色在生成完成时计算并持久化；前端不得在每次加载封面时创建 Canvas 重复计算。
- 主题色计算或持久化失败时生成 job 不得进入 `ready`，必须显式暴露错误。
- 不新增歌词服务；没有逐行歌词字段时只展示真实的“暂无歌词”状态。
- 继续遵守仓库规则：真实问题显式失败，禁止 fallback、静默降级和防御式掩盖。

---

### Task 1: Persist cover theme metadata in the backend

**Files:**
- Modify: `server/yts_server/db/models.py` (MusicCoverJob columns)
- Modify: `server/yts_server/domains/music_covers.py` (`process_next_cover_job`, `_job_response`)
- Modify: database initialization/migration file identified by existing model bootstrap pattern
- Test: `tests/test_music_cover_routes.py`

**Interfaces:**
- Produces `MusicCoverJob.theme_color: str | None` and API field `theme_color` for ready jobs.
- Produces `extract_theme_color(png: bytes) -> str`, raising a concrete error for invalid/unsuitable image data.

- [ ] **Step 1: Write failing tests** for a generated PNG storing a deterministic theme color, API ready response returning it, and extraction failure leaving the job failed.
- [ ] **Step 2: Run** `pytest tests/test_music_cover_routes.py -q` and verify the new assertions fail because the column/helper/response field do not exist.
- [ ] **Step 3: Implement the minimal extractor** in `server/yts_server/domains/cover_color.py`: decode PNG to RGBA with the already packaged `imageio-ffmpeg` binary, ignore alpha-zero and near-black/near-white pixels, quantize RGB buckets, choose the highest weighted bucket, return `#RRGGBB`.
- [ ] **Step 4: Add the nullable theme column** using the repository’s existing SQLite schema initialization/migration convention; do not rewrite unrelated tables.
- [ ] **Step 5: Update `process_next_cover_job`** so PNG signature validation is followed by theme extraction before the artifact is marked ready; persist the color with `output_path` and `output_hash`. Any extractor or write error must flow to `_mark_failed`.
- [ ] **Step 6: Include `theme_color` in `_job_response`** only from persisted job metadata; do not recalculate on status/file reads.
- [ ] **Step 7: Run** `pytest tests/test_music_cover_routes.py -q` and the focused extractor tests; expect PASS.
- [ ] **Step 8: Commit** with `feat: persist generated cover theme colors`.

### Task 2: Add explicit historical cover color backfill

**Files:**
- Create: `server/yts_server/domains/music_cover_backfill.py`
- Modify: existing local maintenance/CLI entrypoint where repository maintenance commands live
- Test: `tests/test_music_cover_routes.py` or a new `tests/test_music_cover_backfill.py`

**Interfaces:**
- Produces `async def backfill_music_cover_theme_colors(sessionmaker) -> int`, which processes only ready jobs with a missing theme color and returns the number updated.

- [ ] **Step 1: Write failing tests** for one ready job without a theme color being updated from its PNG, a second run doing no work, and an invalid PNG being marked failed with an explicit error.
- [ ] **Step 2: Run** the focused backfill test and verify failure.
- [ ] **Step 3: Implement** a bounded query for `status == ready and theme_color is null`; read each `output_path`, call the same extractor as Task 1, persist the value, and mark extraction failures as `failed` with `error_code`/`error_message`.
- [ ] **Step 4: Wire** the function into the existing local maintenance invocation without starting it implicitly on every player request.
- [ ] **Step 5: Run** backfill and cover route tests; expect PASS.
- [ ] **Step 6: Commit** with `feat: backfill legacy cover theme colors`.

### Task 3: Replace the music cover stage with screenshot-aligned layout

**Files:**
- Modify: `desktop/frontend/src/pages/MusicPage.vue`
- Modify or replace: `desktop/frontend/src/components/MusicCoverStage.vue`
- Modify: `desktop/frontend/src/components/YtsAudioPlayer.vue` only where the bottom control/timeline needs to be repositioned without changing emitted events
- Test: `tests/test_music_page_lifecycle.py`, `tests/test_frontend_creator_os_layout.py`

**Interfaces:**
- `MusicCoverStage` consumes `coverUrl`, `themeColor`, `track`, and existing `playing/status` props; emits existing delete/regenerate/retry events.
- `YtsAudioPlayer` retains current `time-update`, `duration-change`, `play`, `pause`, `ended`, seek, volume, and loop events.

- [ ] **Step 1: Add failing static layout assertions** for `aspect-ratio: 1 / 1`, a distinct right-side metadata/lyrics region, a real empty-lyrics state, and removal of the center-label `cover-image` sizing as the main artwork.
- [ ] **Step 2: Run** the focused frontend tests and verify failure.
- [ ] **Step 3: Implement** a stable CSS grid: left square cover and metadata, right information/lyrics column, then the existing player controls across the bottom. Keep responsive one-column stacking for narrow widths.
- [ ] **Step 4: Render the complete cover as the primary `<img>`** with `object-fit: cover`; retain black-vinyl styling only as a low-contrast edge decoration that never clips the cover.
- [ ] **Step 5: Add author/composer labels only from actual track metadata; render `暂无歌词` when no lyrics field exists. Do not invent synchronized lyric content.
- [ ] **Step 6: Run** focused frontend tests and `npm test`/repository frontend test command; expect PASS.
- [ ] **Step 7: Commit** with `feat: redesign music cover player stage`.

### Task 4: Apply persisted theme colors to the player background

**Files:**
- Modify: `desktop/frontend/src/pages/MusicPage.vue`
- Modify: `desktop/frontend/src/components/MusicCoverStage.vue` if theme variables are scoped there
- Modify: `desktop/frontend/src/services/music.js` only if response normalization is required
- Test: `tests/test_music_page_lifecycle.py` and a focused frontend unit/static test

**Interfaces:**
- `coverState.theme_color` is the only source for the current cover theme.
- The stage exposes CSS variables such as `--cover-theme-rgb` and a derived background layer.

- [ ] **Step 1: Add failing tests** asserting theme color is read from the API response and no Canvas/image pixel sampling code is present in the music page path.
- [ ] **Step 2: Implement** request-version guarded theme updates: clear old theme when changing tracks, apply persisted `theme_color` after the new status response, and clear it on delete/unmount.
- [ ] **Step 3: Implement** CSS derivation from the raw color into low-saturation/low-lightness background and glow layers while preserving readable text contrast.
- [ ] **Step 4: Make missing theme metadata an explicit page error for ready covers; do not silently use a hard-coded fallback color.
- [ ] **Step 5: Run** the focused tests and full music-page lifecycle suite; expect PASS.
- [ ] **Step 6: Commit** with `feat: blend music stage with cover theme`.

### Task 5: Verify end-to-end behavior

**Files:**
- Modify: only tests or documentation if verification exposes a real contract gap
- Test: `tests/test_music_cover_routes.py`, `tests/test_music_page_lifecycle.py`, relevant frontend test command

- [ ] **Step 1: Run** `pytest tests/test_music_cover_routes.py tests/test_music_page_lifecycle.py -q`.
- [ ] **Step 2: Run** the frontend lint/build/test command from `desktop/frontend/package.json`.
- [ ] **Step 3: Inspect the rendered desktop and narrow layouts with the existing local dev server; verify square artwork, theme blending, bottom timeline, and no overlapping controls.
- [ ] **Step 4: Run** `git diff --check` and confirm no unrelated files are staged.
- [ ] **Step 5: Commit any test-only correction** with a message describing the concrete contract fixed.
