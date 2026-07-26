# Canonical Audio Playback Rendition Design

## Goal

Preserve every uploaded audio file as an original asset while generating one predictable playback
rendition for Chrome, Safari, and the macOS Tauri WKWebView. New input containers and codecs must
enter the same media pipeline instead of adding player-specific MIME exceptions.

## Decisions

- Preserve original bytes permanently and deduplicate them by SHA-256 content hash.
- Detect the actual container and codec from file bytes. Do not trust the filename suffix or upload
  `Content-Type` as the playback contract.
- Generate playback renditions asynchronously in both local and cloud environments.
- Use versioned profile `aac_lc_m4a_160k_v1`: AAC-LC stereo audio in an M4A container at 160 kbps,
  with response MIME `audio/mp4`.
- Backfill every existing original asset by scanning and enqueueing missing renditions.
- Never fall back to playing the original asset. Unsupported or failed media processing must remain
  visible as an explicit state.

## Data Model

The existing `local_import_blob` and `meta_song` rows continue to describe the original asset.
`meta_song.container_format` must describe the detected container MIME, while `codec_name` describes
the encoded audio. A new playback rendition row contains:

- `original_content_hash`: foreign key to the original asset.
- `profile`: `aac_lc_m4a_160k_v1`.
- `status`: `pending`, `processing`, `ready`, or `failed`.
- `output_hash`, `output_path`, `output_mime`, and `size_bytes` for a ready rendition.
- `error_code` and `error_message` for a failed rendition.
- `attempt_count` and timestamps for diagnosis.

`(original_content_hash, profile)` is unique. The profile is part of artifact identity so a future
encoding change creates a new rendition instead of mutating the meaning of an old one.

## Upload And Processing Flow

1. Read and validate the uploaded bytes.
2. Persist the original file under its content hash.
3. Extract actual audio metadata from the bytes. Reject unrecognized or invalid audio explicitly.
4. Create or locate the original database records and ownership relation.
5. Create the unique rendition row in `pending` state.
6. Return the original asset and rendition state; upload success does not claim playback readiness.
7. A worker claims `pending` work by moving it to `processing` and incrementing `attempt_count`.
8. FFmpeg writes to a temporary output using the exact versioned profile parameters.
9. Validate the output container, codec, duration, and non-empty content.
10. Hash the output, atomically move it to rendition storage, and set the row to `ready`.
11. Any process launch, non-zero exit, or validation failure sets `failed` with an actionable error.

There is no indefinite automatic retry. An explicit retry changes `failed` back to `pending`.

## Playback Contract

Playlist responses expose `playback_status`, `rendition_profile`, and rendition failure information.
The playback file endpoint serves only a `ready` rendition with `Content-Type: audio/mp4`. Requests
for `pending`, `processing`, or `failed` assets return an explicit conflict response and never serve
the original file.

The frontend displays processing and failure states. Only ready tracks receive an object URL and
enter the native audio element. While a visible playlist contains unfinished work, the page polls at
a bounded interval to refresh state. Polling observes state only and never changes failure results.

## Historical Backfill

A repeatable command scans all original asset rows and creates missing rendition tasks. Existing
rows and ready artifacts are skipped. Its summary includes total, created, skipped, ready, and failed
counts. The command exits non-zero when processing finishes with any failed task.

Local and cloud deployments run the same command and use the same FFmpeg profile. Both deployment
artifacts must provide a compatible FFmpeg binary.

## Failure Semantics

- Unknown or invalid input fails upload before a playlist item is created.
- Missing FFmpeg fails the rendition with a dedicated error code.
- A non-zero FFmpeg result stores the bounded stderr diagnosis.
- Invalid output fails validation and is never published.
- Missing database rows or files fail explicitly; they are not reconstructed silently.
- A failed rendition remains failed until an explicit retry.

## Verification

Tests use genuine WAV, MP3, FLAC, and Ogg/Vorbis fixtures rather than relabelled WAV bytes. Coverage
includes byte-based format detection, task uniqueness, state transitions, exact FFmpeg profile,
failed process diagnostics, output validation, `audio/mp4` responses, backfill idempotency, frontend
processing/failure states, and successful metadata loading in the target WKWebView.

