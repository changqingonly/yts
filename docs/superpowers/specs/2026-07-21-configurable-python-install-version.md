# Configurable Python Install Version

## Goal

Allow users to select the Python minor version used by the project-local virtual environment without making installation depend implicitly on the system Python.

## Interface

`./install` uses Python 3.10 by default. Users may explicitly override that version through `YTS_PYTHON_VERSION`:

```bash
YTS_PYTHON_VERSION=3.13 ./install
```

The value is passed unchanged to uv for both interpreter installation and virtual-environment creation.

## Installation Flow

The installer defines `PYTHON_VERSION` from `YTS_PYTHON_VERSION`, defaulting to `3.10`. After installing the project-local uv and Node runtimes, it runs the equivalent of:

```bash
uv python install "${PYTHON_VERSION}"
uv venv --python "${PYTHON_VERSION}" "${ROOT}/.venv"
uv sync --locked
```

All Python dependency resolution remains locked by the committed `uv.lock`.

## Failure Behavior

An invalid, unavailable, or dependency-incompatible requested Python version fails installation at the responsible uv command. The installer does not retry with another interpreter, reuse a different system interpreter, or silently downgrade the request.

## Verification

Static installer contract tests verify:

- the default version is 3.10;
- `YTS_PYTHON_VERSION` overrides the default;
- the selected version is supplied to both `uv python install` and `uv venv --python`;
- dependency installation continues to use `uv sync --locked`.

The full Python test suite and Ruff checks must pass after implementation.
