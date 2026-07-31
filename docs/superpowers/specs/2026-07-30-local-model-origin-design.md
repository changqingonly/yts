# Local Model Origin Design

## Goal

Replace unauthenticated GitHub release discovery for the macOS stable-diffusion.cpp binary with a versioned artifact served by the YTS cloud service. The artifact supports macOS 15 or newer and is suitable as a future CDN origin.

## Scope

- Package only the stable-diffusion.cpp executable and required license material.
- Keep llama.cpp release downloads and all Hugging Face model-weight downloads unchanged.
- Serve immutable artifacts from the cloud service without authentication.
- Make the desktop verify the artifact SHA-256 before extraction and installation.
- Do not add a secondary source, retry fallback, or silent degradation path.

## Artifact Contract

The source revision is pinned to commit `e790073e1c311feb1ff423ba910f398df01bb60e`. The release identifier is the full commit SHA.

The archive is published as `e790073.zip` and contains:

```text
stable-diffusion.cpp-macos-15-arm64/
  sd
  LICENSE
  ggml-LICENSE
  manifest.json
```

`sd` is the arm64 `sd-cli` executable renamed to preserve the desktop gateway command contract. It must be self-contained except for macOS system frameworks and libraries, and its Mach-O deployment target must be exactly macOS 15.0. `manifest.json` records the source repository, source commit, platform, architecture, minimum macOS version, executable path, executable SHA-256, and licenses.

The packaging script rejects the wrong source commit, a missing/non-arm64 executable, non-system dynamic-library dependencies, a deployment target other than 15.0, or a failed `sd --help` smoke test. It writes the archive and a sibling `.sha256` file.

## Server Origin

The cloud service reads artifacts from `YTS_MODEL_ARTIFACT_STORAGE_DIR`, defaulting to `artifacts/download`. It exposes files below:

```text
/download/{artifact_path}
```

For this release the address is:

```text
/download/sd/mac15-arm64/e790073.zip
```

The route uses Starlette file responses, so normal `GET`, `HEAD`, conditional requests, and byte-range requests remain available for CDN origin traffic. Paths are resolved under the configured root; missing artifacts return 404 and traversal attempts cannot escape the root. The service does not generate artifacts at request time.

## Desktop Download Flow

The settings page passes the configured cloud API origin into the Tauri `download_local_models` command. Rust validates that it is an HTTP(S) origin without credentials, query, or fragment, then appends the immutable artifact path.

The stable-diffusion.cpp stage performs these steps in order:

1. Download the archive to a `.part` file.
2. Compute SHA-256 and compare it with the digest compiled into the desktop release.
3. Extract to a temporary directory.
4. Require exactly the declared `sd` executable.
5. Copy it to `app_data_dir()/vendor/sd-bin/sd` and set executable permissions.
6. Remove temporary files only after successful installation.

Any network, status, checksum, archive, layout, or filesystem error is returned to the UI and stops the remaining model download flow. Existing non-empty installed files continue to count as installed; this change does not introduce automatic upgrades.

## Testing

- Server route tests cover GET content, HEAD metadata, byte ranges, missing files, and traversal rejection.
- Packaging-script tests exercise manifest/archive layout and rejection of invalid inputs without rebuilding the upstream project.
- Rust unit tests cover origin validation, immutable URL construction, SHA-256 success, and mismatch failure.
- A real packaging run verifies the produced archive digest, Mach-O deployment target, architecture, dynamic dependencies, and `sd --help` execution on macOS 15.

## Deployment

Run the packaging script on the macOS 15 release builder, copy its version directory into `YTS_MODEL_ARTIFACT_STORAGE_DIR`, and start the cloud service. Verify `HEAD` and a byte-range `GET` against the origin URL before configuring the CDN. The CDN should cache the versioned path as immutable content and use the service URL above as its origin.
