# Configurable Python Install Version Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `./install` use Python 3.10 by default or an explicitly requested version from `YTS_PYTHON_VERSION`.

**Architecture:** Keep version selection inside the existing bootstrap script. Resolve one `PYTHON_VERSION` value once, then pass it explicitly to both uv interpreter installation and virtual-environment creation so the requested version cannot be silently replaced.

**Tech Stack:** Bash, uv, pytest, Ruff

## Global Constraints

- The default Python version is `3.10`.
- `YTS_PYTHON_VERSION` overrides the default value unchanged.
- Invalid or unavailable versions fail at the uv command; there is no fallback or downgrade.
- Dependency installation remains `uv sync --locked` using the committed `uv.lock`.

---

### Task 1: Explicit Python Version Selection

**Files:**
- Modify: `scripts/install.sh:5-10,77-80`
- Modify: `tests/test_servctl.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: optional environment variable `YTS_PYTHON_VERSION`
- Produces: project virtual environment `.venv` created with the selected Python version

- [ ] **Step 1: Write the failing installer contract test**

Add this test to `tests/test_servctl.py`:

```python
def test_install_allows_explicit_python_version_selection() -> None:
    install_source = (_REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert 'PYTHON_VERSION="${YTS_PYTHON_VERSION:-3.10}"' in install_source
    assert 'uv python install "${PYTHON_VERSION}"' in install_source
    assert 'uv venv --python "${PYTHON_VERSION}" "${ROOT}/.venv"' in install_source
    assert "uv python install\n" not in install_source
    assert 'uv venv "${ROOT}/.venv"' not in install_source
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.tools/uv/uv run pytest tests/test_servctl.py::test_install_allows_explicit_python_version_selection
```

Expected: FAIL because `scripts/install.sh` does not define `PYTHON_VERSION` or pass a version to uv.

- [ ] **Step 3: Implement explicit version propagation**

Add near the existing Node version declaration in `scripts/install.sh`:

```bash
PYTHON_VERSION="${YTS_PYTHON_VERSION:-3.10}"
```

Replace the two Python setup commands with:

```bash
uv python install "${PYTHON_VERSION}"
uv venv --python "${PYTHON_VERSION}" "${ROOT}/.venv"
```

Keep `uv sync --locked` unchanged. Do not catch uv failures or select another interpreter.

- [ ] **Step 4: Document the supported invocation**

Add beside the README installation instructions:

```bash
# 默认使用 Python 3.10；可显式选择其他受项目依赖支持的版本
YTS_PYTHON_VERSION=3.13 ./install
```

State that the selected interpreter is installed or reused by project-local uv and used only for `.venv`; it does not replace the system Python.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
.tools/uv/uv run pytest \
  tests/test_servctl.py::test_install_allows_explicit_python_version_selection \
  tests/test_servctl.py::test_locked_install_keeps_root_uv_lockfile_in_source_control
```

Expected: 2 passed.

- [ ] **Step 6: Run full verification**

Run:

```bash
.tools/uv/uv run pytest
.tools/uv/uv run ruff check core server scripts tests
.tools/uv/uv lock --check
git diff --check
```

Expected: 397 tests pass, Ruff reports `All checks passed!`, the lock resolves without changes, and `git diff --check` has no output.

- [ ] **Step 7: Commit the implementation**

```bash
git add scripts/install.sh tests/test_servctl.py README.md
git commit -m "feat: make installer Python version configurable"
```
