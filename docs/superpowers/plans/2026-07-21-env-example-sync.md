# Environment Example Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate tracked, portable, secret-free cloud/local example configurations from ignored real configurations.

**Architecture:** Add one Python command whose parsing and sanitization logic is exposed as pure functions and whose filesystem boundary renders both profiles before replacing either target. Generate the initial examples from the current ignored files, then protect them with unit and repository contract tests.

**Tech Stack:** Python 3.10+, pathlib, urllib.parse, pytest, Ruff

## Global Constraints

- `conf/cloud.env` and `conf/local.env` are local source configurations and remain ignored.
- The generator preserves comments, blank lines, assignment order, variable names, and safe values.
- Sensitive values and machine paths follow the exact mappings in `docs/superpowers/specs/2026-07-21-env-example-sync-design.md`.
- Both profiles must parse and sanitize successfully before either example target is replaced.
- Unknown credential-bearing URLs fail explicitly; there is no fallback or partial generated output.

---

### Task 1: Structured Sanitizer And Atomic Profile Rendering

**Files:**
- Create: `scripts/sync_env_examples.py`
- Create: `tests/test_env_example_sync.py`

**Interfaces:**
- Produces: `render_example(source: str) -> str`
- Produces: `sync_examples(root: Path) -> None`
- Produces: `main() -> int`

- [ ] **Step 1: Write failing parser and sanitizer tests**

Create `tests/test_env_example_sync.py` with synthetic values only. Tests must assert that `render_example` preserves formatting and safe values, empties secret/token fields except the two numeric token settings, replaces database/DSN credentials, applies all seven model path mappings, replaces other absolute paths with `/path/to/value`, and raises `ExampleSyncError` for non-database URLs containing credentials.

Representative assertions:

```python
def test_render_example_preserves_structure_and_sanitizes_values() -> None:
    source = """# profile\nYTS_PROFILE=local\n\nYTS_OPENAI_API_KEY=secret\nYTS_AUTH_ACCESS_TOKEN_TTL_SECONDS=1800\nYTS_DATABASE_URL=postgresql+asyncpg://user:pass@db.internal/yts\nYTS_LLAMA_MODEL=/Users/test/model.gguf\nYTS_AVATAR_STORAGE_DIR=/Users/test/avatars\n"""

    assert render_example(source) == """# profile\nYTS_PROFILE=local\n\nYTS_OPENAI_API_KEY=\nYTS_AUTH_ACCESS_TOKEN_TTL_SECONDS=1800\nYTS_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME\nYTS_LLAMA_MODEL=desktop/vendor/llm-models/Qwen2.5-7B-Instruct-Q4_K_M.gguf\nYTS_AVATAR_STORAGE_DIR=/path/to/value\n"""
```

- [ ] **Step 2: Write the failing all-or-nothing synchronization test**

Use a temporary root containing valid `cloud.env`, an invalid credential-bearing URL in `local.env`, and sentinel example files. Call `sync_examples(tmp_path)`, assert `ExampleSyncError`, then assert both sentinel targets are unchanged.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_env_example_sync.py
```

Expected: collection fails because `scripts.sync_env_examples` does not exist.

- [ ] **Step 4: Implement the structured generator**

Implement `scripts/sync_env_examples.py` with:

```python
ASSIGNMENT_PATTERN = re.compile(
    r"^(?P<prefix>\s*(?:export\s+)?)"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<separator>\s*=\s*)(?P<value>.*)$"
)

SAFE_TOKEN_FIELDS = {
    "YTS_AUTH_ACCESS_TOKEN_TTL_SECONDS",
    "YTS_GATEWAY_TEXT_MAX_TOKENS",
}

PORTABLE_PATHS = {
    "YTS_LLAMA_SERVER_BIN": "desktop/vendor/llama.cpp/build/bin/llama-server",
    "YTS_LLAMA_MODEL": "desktop/vendor/llm-models/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    "YTS_IMAGEGEN_BIN": "desktop/vendor/stable-diffusion.cpp/build/bin/sd",
    "YTS_IMAGEGEN_DIFFUSION_MODEL": "desktop/vendor/sd-models/flux1-schnell-q4_k.gguf",
    "YTS_IMAGEGEN_VAE": "desktop/vendor/sd-models/ae-f16.gguf",
    "YTS_IMAGEGEN_CLIP_L": "desktop/vendor/sd-models/clip_l-q8_0.gguf",
    "YTS_IMAGEGEN_T5XXL": "desktop/vendor/sd-models/t5xxl_q4_k.gguf",
}
```

`render_example` processes every line, preserves blank/comment lines, rejects other non-assignment lines, and delegates values to `_sanitize_value(name, value)`. `_sanitize_value` applies secret names first, exact database placeholders second, portable paths third, absolute paths fourth, and rejects any remaining URL with username/password via `urlsplit`.

`sync_examples` reads and renders both source files into memory first, then writes temporary sibling files and replaces `cloud.example.env` and `local.example.env`. Missing source files and invalid lines raise `ExampleSyncError` with the profile path and line number.

`main` resolves the repository root from `Path(__file__).resolve().parents[1]`, calls `sync_examples`, prints the two generated paths, and returns zero. Do not catch `ExampleSyncError`; command failure must remain visible.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_env_example_sync.py
.venv/bin/ruff check scripts/sync_env_examples.py tests/test_env_example_sync.py
```

Expected: all sanitizer tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 6: Commit generator behavior**

```bash
git add scripts/sync_env_examples.py tests/test_env_example_sync.py
git commit -m "feat: generate sanitized environment examples"
```

---

### Task 2: Generated Examples And Repository Contracts

**Files:**
- Create: `conf/cloud.example.env`
- Create: `conf/local.example.env`
- Modify: `tests/test_env_example_sync.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `sync_examples(root: Path) -> None` from Task 1
- Produces: tracked example configurations accepted by `scripts.servctl.load_profile_env`

- [ ] **Step 1: Generate examples from the ignored real configurations**

Run:

```bash
.venv/bin/python scripts/sync_env_examples.py
```

Expected: both example paths are printed. Inspect only the generated examples, never stage the real `.env` files.

- [ ] **Step 2: Add failing repository contract tests**

Add tests that assert:

```python
@pytest.mark.parametrize("profile", ["cloud", "local"])
def test_committed_example_is_safe_and_parseable(profile: str) -> None:
    root = Path(__file__).resolve().parents[1]
    example_path = root / "conf" / f"{profile}.example.env"
    values = load_profile_env(root, f"{profile}.example")

    assert example_path.is_file()
    assert values["YTS_PROFILE"] == profile
    assert not nonempty_sensitive_fields(values)
    assert not credential_bearing_urls(values)
    assert not undocumented_absolute_paths(values)
```

Also assert via `.gitignore` rules that `conf/*.env` remains ignored and `!conf/*.example.env` remains present.

- [ ] **Step 3: Document the synchronization workflow**

Add to README near profile setup:

```bash
# 修改真实配置字段或安全默认值后，重新生成脱敏模板
./.tools/uv/uv run python scripts/sync_env_examples.py
git diff -- conf/cloud.example.env conf/local.example.env
```

Document that real `.env` files are never staged and that generation fails before replacement when a value cannot be sanitized deterministically.

- [ ] **Step 4: Run repository and full verification**

Run:

```bash
.venv/bin/pytest tests/test_env_example_sync.py tests/test_servctl.py
.venv/bin/pytest
.venv/bin/ruff check core server scripts tests
.tools/uv/uv lock --check
git diff --check
git check-ignore conf/cloud.env conf/local.env
git check-ignore -q conf/cloud.example.env && exit 1 || true
```

Expected: all tests pass, Ruff and lock checks pass, real files are reported as ignored, examples are not ignored, and diff check is empty.

- [ ] **Step 5: Commit generated examples and contracts**

```bash
git add README.md conf/cloud.example.env conf/local.example.env tests/test_env_example_sync.py
git commit -m "chore: publish sanitized environment examples"
```
