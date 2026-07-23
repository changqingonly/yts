# MP4 Audio Playback MIME Preservation

## Problem

Uploaded audio is stored under its SHA-256 hash without a filename extension. The upload path records the browser-provided MIME type in `LocalImportBlob.mime`, but the playback route returns only the extensionless path through `FileResponse`. Starlette therefore emits a generic binary content type instead of the stored MP4 audio type, so the browser cannot reliably select its MP4 audio decoder.

## Design

The authenticated local-import lookup will return a small immutable value containing both the resolved file path and the persisted MIME type. The `/api/music/file/{content_hash}` route will pass both values to `FileResponse`, including the MIME type explicitly as `media_type`.

The ownership check, hash validation, missing database row check, and missing filesystem entry check remain on the existing control path. Missing or invalid data continues to fail explicitly. The implementation will not infer a type from bytes or filenames and will not add a generic fallback.

## Data Flow

1. Upload stores the file bytes and request MIME in `LocalImportBlob`.
2. Playlist playback requests the file by content hash.
3. The domain lookup validates the hash, verifies ownership, loads the blob row, and verifies the stored path exists.
4. The domain lookup returns the stored path and MIME.
5. The route returns the file with the stored MIME as its HTTP `Content-Type`.
6. The frontend preserves that type when converting the response to a Blob URL, allowing the `<audio>` element to select the correct decoder.

## Testing

An integration test will upload content declared as `audio/mp4`, request it through the authenticated playback endpoint, and assert that the response body is unchanged and `Content-Type` starts with `audio/mp4`. The test must fail against the current implementation before production code changes. After the fix, the focused test and the complete music-route test module must pass.
