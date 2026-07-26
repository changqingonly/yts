# Canonical Audio Playback Rendition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve uploaded audio originals and asynchronously produce one browser-safe AAC-LC/M4A playback rendition for every supported input format.

**Architecture:** A persistent `audio_playback_rendition` row is the durable queue and artifact record. An application-lifecycle worker atomically claims pending rows, invokes the bundled FFmpeg executable, validates output with Mutagen, and publishes it atomically; playlist and file APIs expose only the rendition state and ready artifact.

**Tech Stack:** FastAPI lifespan tasks, SQLAlchemy async ORM, Mutagen, imageio-ffmpeg, FFmpeg, Vue 3/Pinia, pytest.

## Global Constraints

- Preserve original bytes and deduplicate by SHA-256.
- Detect container and codec from bytes, not filename or upload MIME.
- Profile is exactly `aac_lc_m4a_160k_v1`: AAC-LC stereo M4A at 160 kbps and `audio/mp4`.
- `(original_content_hash, profile)` is unique and is the idempotency key.
- Valid states are exactly `pending`, `processing`, `ready`, and `failed`.
- Never serve the original file as a playback fallback.
- Failed work remains failed until an explicit retry.
- Local and cloud use the same worker and bundled FFmpeg implementation.

---

### Task 1: Durable rendition model and configuration

**Files:**
- Modify: `server/yts_server/db/models.py`
- Modify: `core/yts_core/config.py`
- Modify: `server/pyproject.toml`
- Modify: `conf/local.env`, `conf/local.example.env`, `conf/cloud.env`, `conf/cloud.example.env`
- Create: `server/yts_server/alembic/versions/20260726_01_audio_playback_rendition.py`
- Test: `tests/test_settings.py`
- Test: `tests/test_music_routes.py`

**Interfaces:**
- Produces: `AudioPlaybackRendition` ORM model and `Settings.playback_rendition_storage_dir`.
- Produces: constants stored as strings: profile, state, artifact identity, error diagnosis, attempts, and timestamps.

- [ ] Add failing settings and schema tests asserting a configurable rendition directory and the unique `(original_content_hash, profile)` database constraint.
- [ ] Run `uv run pytest tests/test_settings.py tests/test_music_routes.py -q` and confirm the new assertions fail.
- [ ] Add `StorageSettings.playback_rendition_dir`, legacy env `YTS_PLAYBACK_RENDITION_STORAGE_DIR`, the ORM model, and an Alembic migration that creates the table and indexes `status`.
- [ ] Add `imageio-ffmpeg>=0.6` so local and cloud resolve the same packaged executable rather than depending on a system command.
- [ ] Run the focused tests and `uv run ruff check core/yts_core/config.py server/yts_server/db/models.py server/yts_server/alembic/versions/20260726_01_audio_playback_rendition.py`.

### Task 2: Byte-based media identification and profile transcoder

**Files:**
- Modify: `server/yts_server/domains/audio_metadata.py`
- Create: `server/yts_server/domains/audio_renditions.py`
- Test: `tests/test_audio_renditions.py`
- Create fixtures: `tests/fixtures/audio/sample.wav`, `sample.mp3`, `sample.flac`, `sample.ogg`

**Interfaces:**
- Produces: `PLAYBACK_PROFILE = "aac_lc_m4a_160k_v1"` and `PLAYBACK_MIME = "audio/mp4"`.
- Produces: `ensure_pending_rendition(session, content_hash) -> AudioPlaybackRendition`.
- Produces: `process_next_pending_rendition(sessionmaker) -> bool` and `retry_failed_rendition(session, content_hash) -> AudioPlaybackRendition`.

- [ ] Generate four tiny genuine fixtures with FFmpeg and add failing tests proving Mutagen identifies their actual container/codec regardless of misleading filename and upload MIME.
- [ ] Add failing unit tests for unique task creation, exact FFmpeg arguments (`-vn -c:a aac -b:a 160k -ac 2 -movflags +faststart`), ready publication, missing executable, non-zero exit, and invalid output.
- [ ] Run `uv run pytest tests/test_audio_renditions.py -q` and confirm failures identify the missing module and behavior.
- [ ] Normalize detected container MIME from the Mutagen parser type and MIME candidates; Ogg/Vorbis must yield `audio/ogg`, while codec remains Vorbis.
- [ ] Implement atomic pending claim, temporary output, FFmpeg execution via `imageio_ffmpeg.get_ffmpeg_exe()`, output validation, SHA-256 naming, atomic move, and explicit failed state with bounded stderr.
- [ ] Run `uv run pytest tests/test_audio_renditions.py -q` and `uv run ruff check server/yts_server/domains/audio_metadata.py server/yts_server/domains/audio_renditions.py tests/test_audio_renditions.py`.

### Task 3: Application worker, upload enqueue, retry, and backfill

**Files:**
- Modify: `server/yts_server/main.py`
- Modify: `server/yts_server/domains/music.py`
- Modify: `server/yts_server/routes/music.py`
- Create: `server/yts_server/audio_backfill.py`
- Modify: `server/pyproject.toml`
- Test: `tests/test_music_routes.py`
- Test: `tests/test_server_lifespan.py`
- Create: `tests/test_audio_backfill.py`

**Interfaces:**
- Consumes: Task 2 enqueue/process/retry APIs.
- Produces: `run_rendition_worker(stop_event)` lifecycle coroutine.
- Produces: `POST /api/music/renditions/{content_hash}/retry`.
- Produces: CLI `yts-audio-backfill` with non-zero exit when any rendition is failed.

- [ ] Add failing route tests asserting upload returns `playback_status=pending`, retry only accepts failed work, and historical rows are enqueued once.
- [ ] Add failing lifespan tests asserting the worker starts after schema bootstrap and is stopped/awaited during shutdown.
- [ ] Implement upload enqueue in the same transaction as original metadata, then signal the durable worker after commit.
- [ ] Implement the lifecycle worker so every startup drains pending rows and newly uploaded rows wake it without busy polling.
- [ ] Implement repeatable backfill summary fields `total`, `created`, `skipped`, `ready`, and `failed`; exit non-zero if `failed > 0`.
- [ ] Run `uv run pytest tests/test_music_routes.py tests/test_server_lifespan.py tests/test_audio_backfill.py -q` and Ruff on changed Python files.

### Task 4: Playback API contract and playlist state

**Files:**
- Modify: `server/yts_server/domains/playlists.py`
- Modify: `server/yts_server/domains/music.py`
- Modify: `server/yts_server/routes/music.py`
- Test: `tests/test_music_routes.py`

**Interfaces:**
- Produces playlist item fields `playback_status`, `rendition_profile`, `playback_error_code`, and `playback_error_message`.
- Produces `GET /api/music/file/{content_hash}` that returns only ready `audio/mp4` rendition bytes.

- [ ] Replace original-file download expectations with failing tests for pending/processing/failed conflict responses and ready M4A bytes with `Content-Type: audio/mp4`.
- [ ] Add failing playlist response tests for every rendition state and explicit failure diagnosis.
- [ ] Batch-load renditions with metadata to avoid per-item queries, and make a missing rendition an explicit contract error rather than inferred readiness.
- [ ] Change file lookup to require owner plus ready rendition and verified artifact path; do not inspect or return `LocalImportBlob.path` for playback.
- [ ] Run `uv run pytest tests/test_music_routes.py -q` and Ruff on the modified domain and route modules.

### Task 5: Frontend processing, failure, retry, and bounded refresh

**Files:**
- Modify: `desktop/frontend/src/services/music.js`
- Modify: `desktop/frontend/src/stores/playlist.js`
- Modify: `desktop/frontend/src/pages/MusicPage.vue`
- Modify: `desktop/frontend/src/components/MusicImportDrawer.vue`
- Test: `tests/test_music_page_lifecycle.py`

**Interfaces:**
- Consumes playlist rendition fields and retry endpoint from Task 4.
- Produces playable object URLs only for `ready` tracks.

- [ ] Add failing source-contract tests for processing copy, failure diagnosis, explicit retry, ready-only object URL loading, and a bounded refresh timer active only while unfinished tracks exist.
- [ ] Update track construction so pending/processing/failed items have no URL and cannot enter playback intent.
- [ ] Render processing and failed states in the playlist/import UI and wire retry to the explicit API.
- [ ] Add one lifecycle-owned refresh timer; clear it on unmount and environment changes, and never convert failed state back to pending locally.
- [ ] Run `uv run pytest tests/test_music_page_lifecycle.py -q` and `npm run build` from `desktop/frontend`.

### Task 6: Packaging, migration, and end-to-end verification

**Files:**
- Modify: `desktop/sidecar/build_macos.spec`
- Modify: `scripts/build_sidecar_macos.sh`
- Modify: `README.md`
- Test: `tests/test_music_routes.py`

**Interfaces:**
- Consumes the imageio-ffmpeg executable from Task 2.
- Produces a sidecar artifact containing that executable and documented cloud deployment/backfill steps.

- [ ] Add a packaging assertion that the resolved FFmpeg executable is collected into the PyInstaller sidecar.
- [ ] Update the build spec to collect imageio-ffmpeg package data/binaries and make the build script fail if the packaged executable is absent.
- [ ] Document `alembic upgrade head`, `yts-audio-backfill`, storage configuration, and failure exit semantics.
- [ ] Run the complete Python suite, Ruff, frontend build, and a real Ogg upload-to-ready-to-download test.
- [ ] Inspect `git diff --check` and confirm unrelated worktree changes were not modified or staged.

