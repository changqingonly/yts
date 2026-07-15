# Desktop Component Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict, versioned desktop component control plane shared by `servctl` and Tauri, with deterministic assets, explicit failures, sanitized frontend configuration, and complete local lifecycle ownership.

**Architecture:** `yts_core.config` becomes the sole profile loader, while `yts_core.components` parses the tracked `desktop/components.toml` contract. `servctl` owns development processes and Tauri owns packaged processes; both resolve the same manifest and honor the same ownership lock. Native producers use structured argv only, and frontend runtime configuration is a separately validated non-secret JSON document.

**Tech Stack:** Python 3.10, Pydantic 2, python-dotenv, tomli, pytest, Rust/Tokio/Axum/Tauri, serde/toml, Vue 3, Node built-in test runner.

---

## File Map

- `core/yts_core/config.py`: canonical strict profile loader and typed settings.
- `core/yts_core/components.py`: strict TOML manifest models, platform selection, path/token resolution.
- `desktop/components.toml`: versioned source/build/model/runtime facts.
- `scripts/servctl/component_commands.py`: install, verify, and status operations.
- `scripts/servctl/supervisor.py`: ownership lock and component process lifecycle.
- `scripts/servctl/runtime_config.py`: sanitized frontend JSON and environment allowlist.
- `desktop/infer-gateway/src/*.rs`: structured producer execution and readiness.
- `desktop/frontend/src/services/runtimeConfig.js`: strict frontend runtime document loader.
- `desktop/src-tauri/src/component_supervisor.rs`: packaged process owner.

### Task 1: Canonical Strict Profile Loader

**Files:**
- Modify: `core/pyproject.toml`
- Modify: `core/yts_core/config.py`
- Create: `conf/local.example.env`
- Create: `conf/cloud.example.env`
- Modify: `tests/conftest.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_servctl.py`

- [ ] **Step 1: Write failing strict-loader tests**

Add focused tests that call the public API below and assert exact failures:

```python
loaded = load_profile_config(
    Profile.LOCAL,
    config_dir=config_dir,
    environ={"YTS_PROFILE": "local"},
)
assert loaded.path == config_dir / "local.env"
assert loaded.settings.profile == Profile.LOCAL
assert loaded.values["YTS_DATABASE_URL"].startswith("sqlite+")
```

Cover missing file, duplicate name, unknown `YTS_` name, profile mismatch, short/empty JWT, missing database URL, postgres checkpoint without DSN, local backend without gateway URL, DeepSeek without key, OpenAI-compatible model without key, and process environment overriding the file. Change the old missing-file-default test to expect `FileNotFoundError`.

- [ ] **Step 2: Verify the tests fail for the intended reasons**

Run:

```bash
PYTHONPATH="$PWD/core:$PWD/server:$PWD" /Users/bytedance/Documents/projects/yts/.venv/bin/python -m pytest -q tests/test_settings.py tests/test_servctl.py
```

Expected: failures show missing `load_profile_config`, duplicate/unknown names being accepted, and missing files using defaults.

- [ ] **Step 3: Implement one strict loader**

Add direct dependencies `python-dotenv>=1.0` and `tomli>=2.0` to `core/pyproject.toml`. In `config.py`, expose this API:

```python
@dataclass(frozen=True)
class LoadedProfileConfig:
    path: Path
    values: dict[str, str]
    settings: Settings


def load_profile_config(
    profile: Profile | str,
    *,
    config_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> LoadedProfileConfig:
    selected_profile = Profile(profile)
    selected_environ = dict(os.environ if environ is None else environ)
    selected_dir = _resolve_config_dir(config_dir, selected_environ)
    path = selected_dir / f"{selected_profile.value}.env"
    file_values = _parse_profile_file(path)
    _validate_profile_name(file_values, selected_profile, path)
    merged = _apply_profile_environment(file_values, selected_environ)
    settings = settings_from_env_mapping(merged)
    _validate_profile_requirements(settings, merged)
    return LoadedProfileConfig(path=path, values=merged, settings=settings)
```

Use python-dotenv for value parsing and a line scanner only for assignment-name/duplicate detection. Allow exactly `YTS_PROFILE` plus `_LEGACY_ENV_MAP` keys in profile files. Reject unknown `YTS_` process variables except the explicit control set `YTS_CONFIG_DIR`, `YTS_SKIP_STARTUP_DB_BOOTSTRAP`, `YTS_PORT`, and `YTS_RUNTIME_DIR`. Apply process environment overrides after file values, construct `settings_from_env_mapping`, then run conditional validation.

Set `SettingsConfigDict(extra="forbid", env_file=None)`. Remove the built-in JWT and checkpoint DSN credentials. Make `get_settings()` select the profile/config directory and call `load_profile_config`; there is no missing-file path returning defaults.

Change `scripts/servctl/config.py` so `require_profile_config`, `load_profile_env`, `validate_profile_config`, `_command_env`, and `_profile_settings` delegate to `load_profile_config`. Retain wrappers only for compatibility and `ServctlError` translation; remove its dotenv loop and provider-specific duplicate validation.

- [ ] **Step 4: Add tracked examples and deterministic test config**

Create both example files with every accepted profile key once, blank secret values, explicit profile, and no vendor command fields. Update the autouse fixture to create a valid temporary `cloud.env`, set `YTS_CONFIG_DIR`, and clear settings caches, while tests that need local create `local.env` explicitly.

- [ ] **Step 5: Verify strict config tests and commit**

Run the command from Step 2 and expect all selected tests to pass. Then commit:

```bash
git add core/pyproject.toml core/yts_core/config.py conf/local.example.env conf/cloud.example.env tests/conftest.py tests/test_settings.py tests/test_servctl.py scripts/servctl/config.py
git commit -m "feat: enforce strict profile configuration"
```

### Task 2: Versioned Component Manifest

**Files:**
- Create: `core/yts_core/components.py`
- Create: `desktop/components.toml`
- Create: `tests/test_component_manifest.py`

- [ ] **Step 1: Write failing manifest contract tests**

Tests must load the real manifest and assert:

```python
manifest = load_component_manifest(repo_root / "desktop" / "components.toml")
assert manifest.schema_version == 1
assert manifest.components["llama"].source.commit == (
    "72874f559c598b8f89fbb24864868337cf5afb4c"
)
assert manifest.components["acestep"].enabled is False
assert manifest.start_order() == ["llama", "stable-diffusion", "infer-gateway"]
```

Also reject unknown fields, duplicate TOML tables, an optional component without explicit `enabled`, unknown dependencies, dependency cycles, unsupported platforms, non-HTTPS model URLs, non-64-character SHA256, zero sizes, shell-string runtime commands, and unknown argv tokens.

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH="$PWD/core:$PWD/server:$PWD" /Users/bytedance/Documents/projects/yts/.venv/bin/python -m pytest -q tests/test_component_manifest.py
```

Expected: import/file failures because neither module nor manifest exists.

- [ ] **Step 3: Implement strict Pydantic manifest models**

Define `ModelAsset`, `SourceSpec`, `BuildSpec`, `ProbeSpec`, `RuntimeSpec`, `ComponentSpec`, and `ComponentManifest`, all with `extra="forbid"`. `RuntimeSpec.argv` is `list[str]`, never a string. Implement `load_component_manifest(path)` as UTF-8 read -> `tomli.loads` -> `ComponentManifest.model_validate`; wrap TOML and validation errors with the manifest path. Implement `current_platform()` with an exhaustive `(platform.system(), platform.machine())` mapping and raise `ValueError` for unsupported pairs. Implement `resolve_component_paths(root, manifest, name)` by resolving every manifest path below `root` or `root / manifest.vendor_dir` and rejecting path traversal. Implement `expand_argv(argv, tokens)` by parsing every `{field}` with `Formatter.parse`, rejecting undeclared fields, and returning a new list without invoking a shell.

Only `{root}`, `{vendor}`, `{source}`, `{build}`, `{artifact}`, and declared `{model:<id>}` tokens are legal in manifest argv. Per-request `{prompt}`, `{out}`, `{width}`, `{height}`, `{steps}`, and `{seconds}` remain unexpanded for the gateway.

- [ ] **Step 4: Add the audited manifest facts**

Add enabled llama, stable-diffusion, and infer-gateway records and disabled ACE-Step. Use pinned revisions from the design. Record the audited model sizes and SHA256 values, `sd-cli` as the stable-diffusion artifact, structured build argv, llama port `8080`, gateway port `8799`, health/readiness URLs, dependencies, and explicit timeouts. No manifest field points at `desktop/vendor/*.env`.

- [ ] **Step 5: Verify and commit**

Run the Task 2 tests and the Task 1 tests. Commit:

```bash
git add core/yts_core/components.py desktop/components.toml tests/test_component_manifest.py
git commit -m "feat: add versioned desktop component manifest"
```

### Task 3: Component Install, Verify, And Status Commands

**Files:**
- Create: `scripts/servctl/component_commands.py`
- Modify: `scripts/servctl/cli.py`
- Modify: `scripts/servctl/__init__.py`
- Create: `tests/test_servctl_components.py`

- [ ] **Step 1: Write failing command tests**

Test real temporary Git repositories and files where practical. Cover:

```python
result = verify_components(root, names=["llama"], hash_file=fake_hash)
assert result[0].state == "ready"
```

Required failures: missing manifest, wrong source remote, wrong commit, dirty source, missing/non-executable artifact, model size mismatch, model hash mismatch, unsupported platform, unknown name, and enabled component depending on disabled component. Assert `status` distinguishes `disabled`, `missing`, `invalid`, `stopped`, `ready`, and `unhealthy`.

Installer tests inject `run_command` and `download` functions and assert clone with the fixed URL, detached checkout of the fixed commit, recursive submodule update, structured configure/build argv, `.partial` download, exact verification, and atomic rename. Dirty sources must fail without reset or checkout.

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH="$PWD/core:$PWD/server:$PWD" /Users/bytedance/Documents/projects/yts/.venv/bin/python -m pytest -q tests/test_servctl_components.py
```

- [ ] **Step 3: Implement component operations**

Expose `install_components(root, names=None, *, run_command=subprocess.check_call, download=_download_model)`, `verify_components(root, names=None, *, hash_file=_sha256_file)`, and `status_components(root, profile, names=None, *, process_exists=_process_exists, http_probe=_http_probe)`. Each returns `list[ComponentResult]`; `ComponentResult` contains `name`, `enabled`, `state`, and `detail`. No public function accepts a shell command string.

Use `subprocess.check_call` with argv lists, `urllib.request.urlopen` streaming to `.partial`, `hashlib.sha256`, exact sizes, `os.replace`, `git status --porcelain`, and PID/HTTP probes. Never invoke a shell, delete a source tree, reset a repository, accept a dirty tree, or treat a non-empty model as valid.

- [ ] **Step 4: Wire the CLI**

Add:

```text
servctl components install
servctl components install llama stable-diffusion
servctl components verify
servctl components verify llama
servctl components status --profile local
servctl components status llama --profile local
```

Return nonzero if any selected enabled component is invalid or unhealthy. Disabled components are successful only when reported as explicitly disabled.

- [ ] **Step 5: Verify and commit**

Run component and existing servctl tests, then commit:

```bash
git add scripts/servctl/component_commands.py scripts/servctl/cli.py scripts/servctl/__init__.py tests/test_servctl_components.py
git commit -m "feat: manage desktop component assets"
```

### Task 4: Gateway Structured Producers And Readiness

**Files:**
- Modify: `desktop/infer-gateway/Cargo.toml`
- Modify: `desktop/infer-gateway/src/main.rs`
- Modify: `desktop/infer-gateway/src/llama.rs`
- Modify: `desktop/infer-gateway/src/image.rs`
- Modify: `desktop/infer-gateway/src/stream.rs`
- Create: `desktop/infer-gateway/src/producer.rs`

- [ ] **Step 1: Write failing Rust unit tests**

Add tests for JSON argv parsing, per-argument token substitution preserving spaces/metacharacters literally, unique temporary paths, enabled-without-argv rejection, disabled image/audio returning `503`, invalid WAV sample rates and corrupt samples returning errors, llama readiness timeout returning `Err`, and aggregate readiness returning non-success.

- [ ] **Step 2: Verify RED**

Run:

```bash
cargo test --manifest-path desktop/infer-gateway/Cargo.toml
```

Expected: tests fail because producer config/readiness APIs do not exist and current fallbacks return successful output.

- [ ] **Step 3: Implement structured producer execution**

`producer.rs` parses JSON arrays from `YTS_IMAGEGEN_ARGV` and `YTS_AUDIOGEN_ARGV`, plus explicit `YTS_IMAGEGEN_ENABLED` and `YTS_AUDIOGEN_ENABLED`. It validates that enabled implies non-empty argv. Substitute each argv element independently and execute with `Command::new(&argv[0]).args(&argv[1..])`. Use `wait_with_output` under `tokio::time::timeout`, kill on timeout, and a unique request directory. Remove it on success and error.

Delete placeholder PNG and synthetic PCM paths. Disabled capabilities return an explicit unavailable error. Any sample decode error or sample-rate mismatch fails.

- [ ] **Step 4: Make llama external and readiness strict**

Remove `YTS_LLAMA_CMD` and child ownership from `LlamaBackend`. `LlamaBackend::connect()` polls the configured base URL and returns an error on timeout. `main()` must complete this check before binding the gateway listener. Add `/ready` using shared application state; it reports capability enablement and text producer reachability.

- [ ] **Step 5: Verify and commit**

Run Rust tests and check. Commit:

```bash
git add desktop/infer-gateway/Cargo.toml desktop/infer-gateway/src
git commit -m "fix: make gateway producers explicit and structured"
```

### Task 5: Sanitized Frontend Runtime Configuration

**Files:**
- Create: `scripts/servctl/runtime_config.py`
- Create: `desktop/frontend/src/services/runtimeConfig.js`
- Create: `desktop/frontend/public/runtime-config.json`
- Create: `desktop/frontend/tests/runtime-config.test.mjs`
- Modify: `desktop/frontend/src/services/environment.js`
- Modify: `desktop/frontend/src/main.js`
- Modify: `desktop/frontend/package.json`
- Modify: `scripts/servctl/config.py`
- Modify: `scripts/servctl/process.py`
- Modify: `tests/test_servctl.py`
- Modify: `tests/test_frontend_lockfile.py`

- [ ] **Step 1: Write failing Python and Node tests**

Python tests assert `_frontend_env` contains only `PATH`, `HOME`, `TMPDIR`, locale/terminal controls, and `VITE_YTS_RUNTIME_CONFIG_URL`, even when backend env contains API keys, JWT, or DSN. Test `write_frontend_runtime_config` produces only schema/profile/default target and endpoint fields.

Node tests call `validateRuntimeConfig` and reject missing targets, unknown top-level keys, invalid URL schemes, secret-shaped keys, and malformed default targets.

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH="$PWD/core:$PWD/server:$PWD" /Users/bytedance/Documents/projects/yts/.venv/bin/python -m pytest -q tests/test_servctl.py tests/test_frontend_lockfile.py
node --test desktop/frontend/tests/runtime-config.test.mjs
```

- [ ] **Step 3: Implement sanitized config generation**

`runtime_config.py` writes JSON atomically to `desktop/frontend/dist/runtime-config.json`. Its data model contains exactly:

```json
{
  "schemaVersion": 1,
  "profile": "local",
  "defaultTarget": "local",
  "targets": {
    "local": {"apiBase": "http://127.0.0.1:8765", "musicWsBase": "ws://127.0.0.1:8799"},
    "cloud": {"apiBase": "http://127.0.0.1:8000", "musicWsBase": "ws://127.0.0.1:8000"}
  }
}
```

`_frontend_env` starts from an allowlist rather than `_command_env`. It never receives profile values.

- [ ] **Step 4: Load before Vue mount and remove hard-coded endpoints**

`loadRuntimeConfig()` fetches `/runtime-config.json` with `cache: "no-store"`, validates it, and configures `environment.js`. `main.js` mounts Vue only after successful loading; on failure it renders a fatal configuration error and throws. There are no endpoint/default fallback constants.

- [ ] **Step 5: Verify and commit**

Run selected Python/Node tests and `npm run build`. Commit all Task 5 files with:

```bash
git commit -m "feat: deliver sanitized frontend runtime config"
```

### Task 6: Servctl Local Supervisor And Ownership

**Files:**
- Create: `scripts/servctl/supervisor.py`
- Modify: `scripts/servctl/commands.py`
- Modify: `scripts/servctl/process.py`
- Modify: `scripts/servctl/health.py`
- Modify: `scripts/servctl/cli.py`
- Modify: `scripts/servctl/__init__.py`
- Modify: `tests/test_servctl.py`
- Create: `tests/test_servctl_local_supervisor.py`

- [ ] **Step 1: Write failing lifecycle tests**

Record calls through injected process/probe functions and assert local startup is exactly:

```python
[
    "lock:servctl",
    "verify:llama",
    "verify:stable-diffusion",
    "verify:infer-gateway",
    "start:llama",
    "ready:llama",
    "start:infer-gateway",
    "ready:infer-gateway",
    "start:backend",
    "write:runtime-config",
    "start:frontend",
]
```

Assert reverse stop order, rollback after failure at every boundary, aggregated stop errors, stale-lock handling only when owner PID is dead, refusal when Tauri owns the lock, component PID/log naming, structured gateway env, and cloud lifecycle remaining free of local components.

Test the gateway environment resolver as an exact, complete dictionary rather than checking individual keys. With the tracked manifest loaded and component paths resolved, require:

```python
image = resolve_component_paths(root, manifest, "stable-diffusion")
assert gateway_env == {
    "YTS_GATEWAY_ADDR": "127.0.0.1:8799",
    "YTS_GATEWAY_SHUTDOWN_TIMEOUT_SECONDS": "15",
    "YTS_LLAMA_BASE_URL": "http://127.0.0.1:8080",
    "YTS_LLAMA_STARTUP_TIMEOUT_SECONDS": "120",
    "YTS_LLAMA_PROBE_TIMEOUT_SECONDS": "2",
    "YTS_LLAMA_COMPLETION_TIMEOUT_SECONDS": "120",
    "YTS_LLAMA_MODEL": "qwen",
    "YTS_IMAGEGEN_ENABLED": "true",
    "YTS_IMAGEGEN_ARGV": json.dumps(
        [
            str(image.artifact),
            "--diffusion-model",
            str(image.models["flux"]),
            "--vae",
            str(image.models["vae"]),
            "--clip_l",
            str(image.models["clip_l"]),
            "--t5xxl",
            str(image.models["t5xxl"]),
            "--prompt",
            "{prompt}",
            "--output",
            "{out}",
            "--width",
            "{width}",
            "--height",
            "{height}",
            "--steps",
            "{steps}",
            "--cfg-scale",
            "1.0",
            "--sampling-method",
            "euler",
        ],
        separators=(",", ":"),
    ),
    "YTS_IMAGEGEN_TIMEOUT_SECONDS": "600",
    "YTS_IMAGEGEN_MAX_OUTPUT_BYTES": "67108864",
    "YTS_IMAGEGEN_MAX_CONCURRENCY": "1",
    "YTS_IMAGEGEN_MAX_WIDTH": "2048",
    "YTS_IMAGEGEN_MAX_HEIGHT": "2048",
    "YTS_IMAGEGEN_MAX_STEPS": "100",
    "YTS_AUDIOGEN_ENABLED": "false",
}
```

Also assert bare IPv6 hosts become `[2001:db8::1]:8799` for `YTS_GATEWAY_ADDR` and `http://[2001:db8::1]:8080` for `YTS_LLAMA_BASE_URL`. Negative tests must reject every missing or wrong-typed source field, zero or multiple llama models, and a llama argv with a missing, duplicate, dangling, or mismatched `--alias`. Assert the disabled ACE-Step service does not add any other `YTS_AUDIOGEN_*` key.

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH="$PWD/core:$PWD/server:$PWD" /Users/bytedance/Documents/projects/yts/.venv/bin/python -m pytest -q tests/test_servctl_local_supervisor.py tests/test_servctl.py
```

- [ ] **Step 3: Implement ownership and process graph**

Create an atomic `run/yts-local-supervisor.lock` JSON file with schema version, owner (`servctl` or `tauri`), PID, and start time. Acquire with exclusive create; validate a pre-existing owner PID and fail if alive. Release only when owner and PID match.

Spawn service components with process groups, PID files, component logs, resolved argv, and manifest timeouts. Build gateway environment from explicit values: llama base URL, image/audio enabled booleans, and JSON argv arrays. Never include command strings.

Implement one strict gateway environment resolver with the following sole mapping contract:

- Map `infer-gateway.runtime.host` plus `port` to `YTS_GATEWAY_ADDR`, using `host:port` for DNS/IPv4 and `[host]:port` for bare IPv6. Map `infer-gateway.runtime.shutdown_timeout_seconds` to `YTS_GATEWAY_SHUTDOWN_TIMEOUT_SECONDS`.
- Map `llama.runtime.host` plus `port` to `YTS_LLAMA_BASE_URL` as an `http://` URL with the same IPv6 bracket rule. Map `llama.runtime.startup_timeout_seconds` to `YTS_LLAMA_STARTUP_TIMEOUT_SECONDS` and `llama.runtime.readiness.timeout_seconds` to `YTS_LLAMA_PROBE_TIMEOUT_SECONDS`.
- Map `infer-gateway.runtime.request_timeout_seconds` only to `YTS_LLAMA_COMPLETION_TIMEOUT_SECONDS`. This is the llama completion request deadline: do not reuse startup/probe timeouts and do not treat it as the FastAPI-to-gateway request timeout.
- Require llama to have exactly one model. Use that model's `id` as `YTS_LLAMA_MODEL`, and require `llama.runtime.argv` to contain exactly one `--alias` immediately followed by the same id. A missing, duplicate, dangling, or mismatched alias is an error. The tracked llama argv is `[..., "--model", "{model:qwen}", "--alias", "qwen"]`; do not add a second schema token for the alias.
- Map `stable-diffusion.enabled` to `YTS_IMAGEGEN_ENABLED`, its path-expanded `runtime.argv` to compact JSON `YTS_IMAGEGEN_ARGV`, `runtime.execution_timeout_seconds` to `YTS_IMAGEGEN_TIMEOUT_SECONDS`, and its limits to `YTS_IMAGEGEN_MAX_OUTPUT_BYTES`, `YTS_IMAGEGEN_MAX_CONCURRENCY`, `YTS_IMAGEGEN_MAX_WIDTH`, `YTS_IMAGEGEN_MAX_HEIGHT`, and `YTS_IMAGEGEN_MAX_STEPS`.
- ACE-Step is currently a service component with `enabled = false`. Emit only `YTS_AUDIOGEN_ENABLED=false`; never map its service argv to `YTS_AUDIOGEN_ARGV`, and omit every other `YTS_AUDIOGEN_*` variable. Audio mapping may be added only after the versioned manifest contains a command adapter with the complete command limits required by the gateway.

Every source field above is required for its mapping and must have the schema-defined type. Missing fields, wrong runtime kinds, incomplete limits, or inconsistent component facts fail explicitly; the resolver has no default values, hard-coded ports/timeouts, or synthesized argv.

- [ ] **Step 4: Integrate start/stop/status**

For local start, verify/install separation is strict: missing assets fail with a command telling the user to run `servctl components install`; start never downloads. On failure unwind only processes started by this invocation. Local stop is frontend, backend, gateway, producer, then lock. Include component results in `servctl status local`.

- [ ] **Step 5: Verify and commit**

Run local supervisor, component, and existing servctl tests. Commit:

```bash
git add scripts/servctl tests/test_servctl.py tests/test_servctl_local_supervisor.py
git commit -m "feat: supervise the complete local service graph"
```

### Task 7: Tauri Packaged Supervisor

**Files:**
- Create: `desktop/src-tauri/src/component_supervisor.rs`
- Modify: `desktop/src-tauri/src/lib.rs`
- Modify: `desktop/src-tauri/src/sidecar.rs`
- Modify: `desktop/src-tauri/Cargo.toml`
- Modify: `desktop/src-tauri/tauri.conf.json`

- [ ] **Step 1: Write failing Rust tests**

Test manifest deserialization, current-platform matching, topological order, lock refusal when a live `servctl` PID owns it, child retention, start rollback, and reverse stop. Use a fake launcher trait returning deterministic child handles; do not depend on native models.

- [ ] **Step 2: Verify RED**

Run:

```bash
cargo test --manifest-path desktop/src-tauri/Cargo.toml
```

- [ ] **Step 3: Implement managed supervisor state**

Add `toml`, `fs2`, and required serde support. `ComponentSupervisor` owns the lock file and ordered child handles. It reads `desktop/components.toml` in development and the installed resource/app-data manifest in packaged builds, resolves structured argv without a shell, starts enabled service producers, waits readiness, starts gateway, then starts sidecar with explicit `YTS_PROFILE=local`, `YTS_CONFIG_DIR`, and `YTS_RUNTIME_DIR`.

Store the supervisor with `app.manage`. `start_local_runtime` and `stop_local_runtime` commands mutate that state. Release the lock only after all owned children stop. Debug builds require explicit start; release setup starts the runtime and fails application setup if configuration or readiness fails.

- [ ] **Step 4: Remove sidecar stub ownership**

Route existing sidecar commands through `ComponentSupervisor`; do not discard child or receiver handles. Add required `externalBin`/resource declarations for the sidecar, gateway, and manifest without bundling model files.

- [ ] **Step 5: Verify and commit**

Run Tauri tests and `cargo check`. Commit:

```bash
git add desktop/src-tauri
git commit -m "feat: supervise packaged desktop processes in Tauri"
```

### Task 8: Remove Obsolete Vendor Configuration And Verify End To End

**Files:**
- Modify: `scripts/build_llamacpp.sh`
- Modify: `scripts/build_sdcpp.sh`
- Modify: `scripts/build_acestep.sh`
- Modify: `scripts/dev_gateway.sh`
- Modify: `README.md`
- Modify: `.gitignore`
- Create: `tests/test_desktop_component_source_contract.py`

- [ ] **Step 1: Write failing source-contract tests**

Assert no tracked script reads or writes `desktop/vendor/*.env`, no build script clones a floating branch, no model validity check uses only `-s`, no script advertises placeholder/synthetic behavior, Cargo application lockfiles are trackable, and README uses `servctl components install|verify|status` plus `servctl start --profile local` as the supported flow.

- [ ] **Step 2: Verify RED**

Run the new source-contract tests; expect failures against the legacy scripts and README.

- [ ] **Step 3: Replace legacy entry points**

Make `build_llamacpp.sh`, `build_sdcpp.sh`, and `build_acestep.sh` exec `./servctl components install llama`, `stable-diffusion`, and `acestep` respectively. Make `dev_gateway.sh` fail with a message directing users to `./servctl start --profile local`; it must not source generated env files. Stop ignoring all Cargo lockfiles and force-add lockfiles for the two application crates.

- [ ] **Step 4: Run complete verification**

Run, in order:

```bash
PYTHONPATH="$PWD/core:$PWD/server:$PWD" /Users/bytedance/Documents/projects/yts/.venv/bin/python -m pytest -q
node --test desktop/frontend/tests/runtime-config.test.mjs
npm --prefix desktop/frontend run build
cargo test --manifest-path desktop/infer-gateway/Cargo.toml
cargo check --manifest-path desktop/infer-gateway/Cargo.toml
cargo test --manifest-path desktop/src-tauri/Cargo.toml
cargo check --manifest-path desktop/src-tauri/Cargo.toml
bash -n servctl install scripts/*.sh
```

Expected: every command exits `0`; pytest reports no failures; both Rust crates compile and test; frontend build produces `dist/index.html` and `dist/runtime-config.json`.

- [ ] **Step 5: Verify the live non-mutating command surface and commit**

Run `./servctl --help`, `./servctl components status --profile local`, and `./servctl status --profile cloud`. Do not run install or start during verification. Commit:

```bash
git add -A
git commit -m "docs: make component manager the supported local workflow"
```

## Plan Self-Review

- Every approved design requirement maps to at least one task.
- Configuration parsing has one owner; component TOML remains a separate typed contract.
- Install and start are separate, so startup never performs network or destructive cache mutations.
- Optional behavior is represented only by explicit `enabled = false`.
- Both process owners use the same manifest and lock contract.
- All external commands are argv arrays; no shell execution or silent fallback remains.
