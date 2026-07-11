# Desktop Component Management Design

## Status

Approved by the user on 2026-07-11. This document records the approved design before implementation.

## Problem

The local desktop runtime currently has three unrelated control planes:

- `conf/{profile}.env` configures Python application behavior.
- generated files under `desktop/vendor/*.env` configure native producers.
- `servctl` manages only FastAPI and Vite, while `dev_gateway.sh` starts the gateway manually.

`desktop/vendor` also mixes source repositories, build outputs, models, and generated configuration. The directory is ignored by Git, so it cannot define component versions or runtime behavior. Missing producers currently trigger placeholders or synthetic output, and gateway health does not represent producer readiness.

## Goals

1. Make one versioned manifest the source of truth for local native components.
2. Make `desktop/vendor` a disposable cache that can be rebuilt from the manifest.
3. Make `yts_core.config` the only profile dotenv parser and validator.
4. Give `servctl` complete development and operations ownership of the local process graph.
5. Give the packaged Tauri application ownership of its own process graph, with an ownership lock preventing concurrent `servctl` control.
6. Remove shell command templates, placeholder output, synthetic output, and implicit external-process assumptions.
7. Expose only non-secret runtime configuration to the frontend.

## Non-Goals

- Implementing the ACE-Step request protocol. ACE-Step remains explicitly disabled until its HTTP or request-file adapter exists.
- Bundling multi-gigabyte models into the Tauri application.
- Downloading or building components during `servctl start`. Installation is an explicit command.
- Supporting Windows component builds in this iteration. Unsupported platforms fail explicitly.

## Versioned Component Manifest

`desktop/components.toml` is tracked in Git. Each component declares:

- stable identifier, kind, and explicit `enabled` value;
- supported platform identifiers;
- dependencies;
- source URL, pinned commit, submodule policy, and cache source directory for external sources;
- structured configure/build argv and expected artifact;
- model URL, exact byte size, SHA256, and cache path;
- structured runtime argv with token placeholders resolved without a shell;
- host, port, health URL, readiness URL, startup timeout, and shutdown timeout for services.

External components are pinned to the currently audited revisions:

- llama.cpp: `72874f559c598b8f89fbb24864868337cf5afb4c`
- stable-diffusion.cpp: `e790073e1c311feb1ff423ba910f398df01bb60e`
- acestep.cpp: `da5bc90f8664c242a7bb42eaa0c778762c02c6e3`

ACE-Step is present with `enabled = false`. Disabled is a first-class state; an absent command or model never means disabled.

## Cache Semantics

`desktop/vendor` contains only materialized cache data:

- cloned source trees;
- build directories and native artifacts;
- downloaded model files.

No generated `.env`, runtime command string, selected version, or enabled state is read from this directory. A user can delete the directory and reconstruct every enabled component with `servctl components install`.

Installation refuses dirty or wrong-remote source trees. It never resets or overwrites local source changes. Model downloads use a temporary partial file, then require exact size and SHA256 before atomic replacement.

## Strict Profile Configuration

`yts_core.config.load_profile_config` owns profile loading. It:

1. selects one explicit profile and config directory;
2. requires `conf/{profile}.env` to exist;
3. parses dotenv syntax once;
4. rejects invalid lines, duplicate names, and unknown `YTS_` profile names;
5. requires the file's `YTS_PROFILE` to match the selected profile;
6. applies documented process-environment overrides;
7. constructs typed `Settings`;
8. validates conditional requirements for auth, database, checkpointing, and the selected inference provider.

Public `conf/local.example.env` and `conf/cloud.example.env` files document all accepted profile keys without real secrets. Real profile files remain ignored. Built-in JWT and database credentials are removed.

`servctl` may adapt exceptions to `ServctlError`, but it does not parse dotenv or maintain its own schema.

## Process Ownership And Lifecycle

For `cloud`, `servctl` keeps the existing FastAPI then frontend lifecycle.

For `local`, `servctl start` performs:

1. acquire the local supervisor ownership lock;
2. strictly load the local profile and component manifest;
3. verify every enabled component, source revision, artifact, and model;
4. start long-lived producer services in dependency order;
5. wait for producer readiness;
6. start infer-gateway with resolved structured component configuration;
7. wait for gateway readiness;
8. run the existing FastAPI preflight and start FastAPI;
9. write sanitized frontend runtime configuration;
10. start the frontend.

Failure unwinds every process started by the command in reverse order. `stop local` also stops in exact reverse order and reports all failures. PID files, process groups, log files, health checks, and timeouts are managed consistently.

`servctl components` exposes:

- `install [names...]`: clone/fetch pinned sources, build artifacts, download and verify models;
- `verify [names...]`: perform immutable source/artifact/model validation without mutation;
- `status [names...]`: report disabled, missing, invalid, stopped, starting, ready, or unhealthy states.

`servctl status local` includes component and gateway state in addition to FastAPI and frontend state.

## Gateway Contract

The gateway no longer starts llama through `sh -c`. Its text producer must already be ready when the gateway starts.

Image and audio command producers receive JSON argv arrays. Placeholders are substituted per argument and passed to `Command::new`; a shell is never involved. Temporary output paths are unique per request, stdout and stderr are drained safely, execution has an explicit timeout, and temporary files are removed on every exit path.

Capability state is explicit:

- enabled with missing configuration is a startup error;
- disabled returns a clear unavailable response;
- no image placeholder or music synthesizer exists;
- invalid WAV sample rate or samples fail rather than warn and continue.

`/health` is process liveness. `/ready` reports aggregate readiness and returns a non-success response while any required capability is unavailable.

## Frontend Runtime Configuration

The frontend loads `/runtime-config.json` before mounting Vue. The document contains only:

- default target;
- API and music WebSocket endpoints for local and cloud;
- profile and schema version.

The loader rejects missing files, unknown targets, invalid schemes, and malformed values. It has no fallback constants. `servctl` passes only a small allowlist of operating-system variables to npm and never passes profile secrets, JWT, API keys, or database URLs.

## Tauri Supervisor

Tauri owns packaged-desktop processes and stores child handles in managed application state. It consumes the same versioned manifest, validates explicit enabled state and platform, acquires the same ownership-lock format, starts producers then gateway then sidecar, and stops them in reverse order.

Tauri never invokes `servctl`. `servctl` never controls a packaged application. In development, the ownership lock prevents both supervisors from managing the same runtime directory simultaneously.

## Testing

- Python unit tests cover strict dotenv behavior, manifest parsing, source/model verification, install behavior, lifecycle ordering, rollback, ownership, status, and frontend env sanitization.
- Rust unit tests cover structured argv substitution, disabled capability errors, manifest parsing, and supervisor ordering/state.
- Frontend tests cover runtime config validation and removal of hard-coded endpoints.
- Integration tests cover `servctl start local` ordering with real subprocess boundaries replaced only at the process-launch edge.
- Existing Python, frontend source-contract, shell syntax, Rust check/test, and build checks remain green.

## Migration

1. Land strict configuration and versioned examples.
2. Land manifest parsing plus `components verify/install/status`.
3. Replace gateway shell/fallback behavior.
4. Extend `servctl` local lifecycle and frontend runtime config.
5. Enable the Tauri supervisor and ownership lock.
6. Remove generated vendor env consumption and obsolete build-script claims.

At every stage, an invalid or incomplete configuration fails explicitly; no compatibility fallback is introduced.
