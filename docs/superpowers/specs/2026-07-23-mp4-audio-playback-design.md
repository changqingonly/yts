# MP4 Audio Playback MIME Preservation

## Problem

Uploaded audio is stored under its SHA-256 hash without a filename extension. Browsers commonly declare an audio-only `.mp4` upload as `video/mp4`, while Mutagen identifies the actual AAC audio container as `audio/mp4`. The playback route must therefore use the persisted content-derived container MIME instead of the upload declaration or filename inference.

## Design

The authenticated local-import lookup will load both `LocalImportBlob` and `MetaSong`, then return a small immutable value containing the resolved file path and `MetaSong.container_format`. The `/api/music/file/{content_hash}` route will pass both values to `FileResponse`, including the content-derived MIME type explicitly as `media_type`.

The ownership check, hash validation, missing blob row check, missing metadata row check, missing container MIME check, and missing filesystem entry check remain explicit. The playback request will not fall back to the browser upload declaration, filename inference, or a generic MIME type.

## Data Flow

1. Upload stores the file bytes and request MIME in `LocalImportBlob`, and stores Mutagen's content-derived container MIME in `MetaSong.container_format`.
2. Playlist playback requests the file by content hash.
3. The domain lookup validates the hash, verifies ownership, loads the blob and metadata rows, verifies the container MIME, and verifies the stored path exists.
4. The domain lookup returns the stored path and content-derived container MIME.
5. The route returns the file with the content-derived MIME as its HTTP `Content-Type`.
6. The frontend preserves that type when converting the response to a Blob URL, allowing the `<audio>` element to select the correct decoder.

## Testing

An integration test will upload valid audio content with the browser-style declaration `video/mp4`, request it through the authenticated playback endpoint, and assert that the response body is unchanged and `Content-Type` is the extractor-derived `audio/wav` for the self-contained WAV fixture. This proves that playback ignores an incorrect upload declaration and also covers previously stored rows with the wrong MIME. The test must fail against the current implementation before production code changes. After the fix, the focused test and the complete music-route test module must pass.
