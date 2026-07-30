# Local Model Origin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and serve a macOS 15 stable-diffusion.cpp artifact from the YTS server and install it from the desktop with mandatory SHA-256 verification.

**Architecture:** A deterministic shell script packages a pinned arm64 binary into an immutable version directory. FastAPI mounts the configured artifact root at a public origin path, while the desktop constructs that path from its cloud API origin and verifies the compiled digest before extraction.

**Tech Stack:** Bash, CMake, macOS Mach-O tools, FastAPI/Starlette, Rust/Tauri, reqwest, sha2, pytest, Cargo tests.

## Global Constraints

- Minimum supported operating system is macOS 15.0.
- stable-diffusion.cpp source commit is `e790073e1c311feb1ff423ba910f398df01bb60e`.
- Artifact filename is `stable-diffusion.cpp-macos-15-arm64.zip`.
- Download and integrity failures stop installation and are surfaced to the UI.
- No fallback source or silent degradation is permitted.
- Model weights remain on their existing Hugging Face download paths.

---

### Task 1: Server Artifact Origin

**Files:**
- Modify: `core/yts_core/config.py`
- Modify: `server/yts_server/main.py`
- Modify: `conf/cloud.example.env`
- Modify: `conf/local.example.env`
- Create: `tests/test_model_artifact_origin.py`

**Interfaces:**
- Consumes: `YTS_MODEL_ARTIFACT_STORAGE_DIR` from the existing settings loader.
- Produces: public `GET`/`HEAD /artifacts/local-models/{path}` responses.

- [ ] Write tests that create an artifact root, request a file with GET/HEAD/Range, and assert 404 for missing or traversal paths.
- [ ] Run `./.venv/bin/pytest tests/test_model_artifact_origin.py -q` and confirm failure because the route is absent.
- [ ] Add `storage.model_artifact_dir`, its legacy environment mapping/property, and mount `StaticFiles` with `check_dir=True` at `/artifacts/local-models`.
- [ ] Add the storage setting to both example environment files.
- [ ] Re-run the focused test and `tests/test_settings.py tests/test_env_example_sync.py`.

### Task 2: Reproducible macOS Artifact Packaging

**Files:**
- Create: `scripts/package_sdcpp_macos.sh`
- Create: `tests/test_sdcpp_artifact_packaging.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: pinned checkout at `desktop/vendor/stable-diffusion.cpp` and its `build/bin/sd-cli` output.
- Produces: `artifacts/local-models/stable-diffusion.cpp/<commit>/stable-diffusion.cpp-macos-15-arm64.zip` plus `.sha256`.

- [ ] Write a test fixture containing fake inspection tools and a fake source tree, then assert the archive layout and manifest fields.
- [ ] Run `./.venv/bin/pytest tests/test_sdcpp_artifact_packaging.py -q` and confirm failure because the script is absent.
- [ ] Implement the script with explicit commit, architecture, deployment-target, dependency, license, smoke-test, manifest, archive, and digest checks.
- [ ] Re-run the focused test.
- [ ] Run the script against the real pinned checkout and inspect the resulting archive and digest.

### Task 3: Desktop Immutable Download and Integrity Check

**Files:**
- Modify: `desktop/src-tauri/Cargo.toml`
- Modify: `desktop/src-tauri/src/models.rs`
- Modify: `desktop/frontend/src/services/desktop.js`
- Modify: `desktop/frontend/src/pages/SettingsPage.vue`
- Modify: `tests/test_frontend_workspace_layout.py`

**Interfaces:**
- Consumes: cloud API origin string and the immutable archive URL from Tasks 1 and 2.
- Produces: `download_local_models(app, artifact_origin)` with verified stable-diffusion.cpp installation.

- [ ] Add Rust unit tests for accepted/rejected origins, exact URL construction, and SHA-256 verification.
- [ ] Run `cargo test --manifest-path desktop/src-tauri/Cargo.toml models::tests` and confirm failure for missing functions.
- [ ] Add `sha2`, fixed artifact constants, strict origin parsing, digest calculation, and the fixed archive download path; remove GitHub release lookup for stable-diffusion.cpp only.
- [ ] Pass `apiBase("cloud")` from the settings page through the frontend service into Tauri.
- [ ] Update the frontend contract test and run focused Rust/frontend tests.

### Task 4: Documentation and End-to-End Verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: artifact script, origin route, and desktop URL contract from Tasks 1-3.
- Produces: operator instructions for building, publishing, and probing the CDN origin.

- [ ] Document the immutable origin URL, packaging command, storage configuration, SHA-256 publication, and HEAD/Range verification commands.
- [ ] Run Python focused tests, Rust tests, frontend tests, formatting checks, and release builds affected by the change.
- [ ] Start the cloud server with the generated artifact root and verify HEAD plus a byte-range GET against the actual origin route.
- [ ] Review `git diff` to ensure unrelated user changes remain intact and no generated binary is staged.
