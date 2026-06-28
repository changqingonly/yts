# YTS Creator OS Full Yuetools Migration Design

## Decision

Adopt the Creator OS product shell and migrate the relevant yuetools product capabilities in full.

The target product is no longer only a workflow editor. YTS becomes a logged-in creator app with these primary tabs:

- Music: default landing page and music player.
- Creation: current Pro lyrics workflow.
- Assets: user-owned creative assets.
- Messages: future user notifications and system messages.
- Settings: model, account, preferences, and app settings.
- User profile: avatar, nickname, gender, birthday, bio, login/logout.

The migration copies yuetools behavior and rules, but the implementation must be translated into the YTS architecture: Python/FastAPI server, transport-agnostic `core/`, Vue desktop frontend, and thin HTTP/desktop entrypoints. Rust service code from yuetools is the behavior source, not a module to embed directly.

## Scope

### In Scope

User and auth:

- Register, login, logout, current user.
- Personal profile: gender, birthday, bio, nickname/username, avatar upload, default avatar.
- Password transport and storage copied from yuetools:
  - Issue one-time RSA-OAEP-256 public key for register/login.
  - Client encrypts password with Web Crypto.
  - Server decrypts once with cached private key.
  - Server stores Argon2id password hash.
  - Password policy: 8-200 chars, must contain ASCII letter and digit.
- Access-token based route protection.

Credits and usage control:

- Credit account, ledger, grant record, reservation.
- Daily login grant, welcome register grant.
- Generation charge flow copied from yuetools: reserve -> capture on success, release on failure.
- Daily usage quota:
  - Lyrics generation: max 100 per user per day.
  - Image generation: max 100 per user per day.
  - Audio effects: max 100 per user per day.
- Quota failures are explicit API errors. No silent fallback to local counters.

Assets:

- Song inspiration assets with clue, title, style prompt, lyric.
- Song list/detail/update/delete behavior copied from yuetools song APIs.
- Creation output can be saved into assets.
- Image gallery and audio effects tabs exist in Assets, with persisted empty-state metadata and quota display. Actual generation engines are not considered complete until their backend endpoints exist and pass quota checks.

Music:

- Default page is music player.
- Playlist sync, local audio import, file streaming, and owner authorization are copied from yuetools behavior.
- Desktop can support local/offline music access using existing yuetools offline-auth rules after auth migration.
- Mini player remains globally visible when audio is playing.

Creation:

- Existing YTS Pro lyrics workflow remains the Creation tab.
- Existing workflow debugging views become advanced controls/drawers.
- Normal creator workflow foregrounds prompt input, current output, assets saving, quota/credit status, and progress.

Settings:

- Profile settings.
- Model settings and local/platform model preferences following yuetools Settings page shape.
- Logout entry.
- Credit balance and ledger entry point.

### Target But Provider-Gated

These remain full-copy target capabilities. If YTS does not yet have the matching provider or runtime wiring, the UI may expose the product entry, but the backend must return an explicit not-implemented error until the real provider is wired and tested:

- Image generation model integration.
- Audio effects generation.
- Admin debug pages unless explicitly requested.
- WebSocket realtime channel unless required by migrated notifications or playlist sync.
- Full desktop updater migration.

If a migrated UI entry depends on one of these unavailable backends, it must show "待建设" and the API must return an explicit not-implemented error rather than pretending to generate. This is not a fallback and not a silent degradation; it is a visible incomplete capability gate.

## Product Information Architecture

### Global Shell

The app uses a persistent left navigation rail:

1. Music
2. Creation
3. Assets
4. Messages
5. Settings
6. Profile avatar/login state at bottom

The top area of each page shows page-local context and global account affordances:

- User avatar or login button.
- Credit balance.
- Daily quota chips for lyrics, images, and audio effects.
- Target selector for local/cloud when relevant.

The shell must avoid the current workflow-editor-only framing. "YTS Studio" can remain the product mark, but the primary mental model is "creator workspace with music playback, creation, and assets."

### Music Tab

Music is the default route.

Main regions:

- Current track cover/waveform area.
- Playback controls.
- Lyrics display if available.
- Queue/playlists.
- Import local audio.
- Recent generated songs linking to Assets detail.
- Global mini player when navigating away.

Empty state:

- "暂无播放内容" with import and open-assets actions.

### Creation Tab

Creation hosts the existing Pro lyrics workflow.

Default creator view:

- Prompt input.
- Run action.
- Current generated title/style/lyrics.
- Progress by stage.
- Save to Assets.
- Credit/quota state.

Advanced view:

- Flow graph.
- Node config.
- Trace.
- LLM input/output.
- Prompt pack/debug details.

Advanced views should be drawers or secondary tabs, not first-screen dominant content.

### Assets Tab

Assets has three sub-tabs:

- Song Inspiration: implemented fully.
- Image Gallery: target tab, explicit "待建设" until backend exists.
- Audio Effects: target tab, explicit "待建设" until backend exists.

Song Inspiration fields:

- clue
- title
- style_prompt
- lyric
- source prompt
- model/provider
- version
- created_at / updated_at

Actions:

- open detail
- copy style prompt
- copy lyric
- reuse in Creation
- add to Music if audio exists
- delete/update

### User And Settings

Auth pages:

- Login
- Register
- Agreement

Profile settings:

- avatar
- nickname/username
- gender
- birthday
- bio

Settings:

- Account/profile.
- Model preferences.
- Credits and usage ledger.
- Local/desktop preferences.

## Backend Architecture

YTS must keep its architecture boundary:

- `core/`: transport-agnostic business rules and orchestration.
- `server/`: FastAPI routes, request/response schemas, auth dependencies.
- `desktop/sidecar`: thin local entrypoint reusing server app.

Business logic must not be implemented inside FastAPI route handlers.

### Required Domains

Auth domain:

- UserAccount.
- UserSession.
- Password key cache.
- Access token service.
- Profile service.
- Avatar storage service.

Credits domain:

- CreditAccount.
- CreditLedger.
- CreditGrantRecord.
- CreditReservation.
- CreditPolicyService.
- CreditReservationGuard.
- Daily quota service.

Assets domain:

- SongAsset or SongPrompt/SongDetail equivalent.
- Asset ownership checks.
- Song save/list/detail/update/delete service.

Music domain:

- Playlist.
- PlaylistItem.
- LocalImportBlob.
- LocalImportOwner.
- LocalImportService.
- PlaylistSyncService.

Creation integration:

- Current `/api/workflows/...` and `/api/creation` routes must be protected by auth in cloud mode.
- Creation run must check daily lyrics quota and credit reservation before LLM execution.
- On success: capture credit and increment usage.
- On failure: release credit and do not increment successful generation count unless the policy intentionally counts attempts. For the requested "最多100次", the design uses attempts started after successful reservation, so the quota service increments when generation is admitted. If generation fails after admission, credit releases but usage remains consumed to prevent retry storms.

## API Surface

Auth:

- `GET /api/auth/register_key`
- `GET /api/auth/login_key`
- `GET /api/auth/register_check`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

User:

- `GET /api/user/profile`
- `PUT /api/user/profile`
- `POST /api/user/avatar/upload`
- `GET /static/user/avatar/default/{seed}`
- `GET /static/user/avatar/uploaded/{file_name}`

Credits and quotas:

- `GET /api/credits/balance`
- `GET /api/credits/ledger`
- `GET /api/usage/daily`

Assets:

- `POST /api/song/save`
- `GET /api/song/list`
- `GET /api/song/{id}`
- `PUT /api/song/{id}`
- `DELETE /api/song/{id}`
- `GET /api/assets/summary`

Music:

- `POST /api/music/playlist/sync`
- `POST /api/music/local_import/upload`
- `GET /api/music/local_import/file/{hash}`

Creation:

- Existing YTS creation/workflow APIs remain.
- Cloud mode requires auth.
- Lyrics generation scene uses lyrics quota and credit reservation.

Provider-gated features:

- `POST /api/images/generate` and `POST /api/audio-effects/generate` must return explicit not-implemented until real services exist.
- They still must expose quota state in `GET /api/usage/daily`.

## Data Model

Use SQLAlchemy models in `server/yts_server/db/models.py` or split model files by domain if the file becomes too large.

Required tables:

- `user_account`
- `user_session`
- `credit_account`
- `credit_ledger`
- `credit_grant_record`
- `credit_reservation`
- `daily_usage_counter`
- `song_prompt`
- `song_detail`
- `song_asset`
- `music_playlist`
- `music_playlist_item`
- `local_import_blob`
- `local_import_owner`

Core fields should mirror yuetools names where practical to reduce migration friction. Existing `CreationJob` should not be repurposed for user assets.

## Error Handling

Failures must be explicit:

- Missing auth returns 401.
- Insufficient credits returns a typed 402/400 style API error with code.
- Daily quota exhausted returns a typed quota error.
- Password key expired returns a typed bad request.
- Unsupported image/audio generation returns a typed not-implemented error.
- DB unavailable fails the request; no in-memory fallback for auth, credits, usage, or assets.

No defensive fallback should mask persistence, auth, or billing failures.

## Frontend Architecture

YTS frontend should move from one large `App.vue` toward feature modules:

- `src/app/AppShell.vue`
- `src/router/index.js`
- `src/stores/auth.js`
- `src/stores/player.js`
- `src/stores/playlist.js`
- `src/features/auth/*`
- `src/features/credits/*`
- `src/features/assets/*`
- `src/features/music/*`
- `src/features/creation/*`
- `src/pages/MusicPage.vue`
- `src/pages/CreationPage.vue`
- `src/pages/AssetsPage.vue`
- `src/pages/LoginPage.vue`
- `src/pages/RegisterPage.vue`
- `src/pages/ProfileSetupPage.vue`
- `src/pages/SettingsPage.vue`

The current workflow editor UI should become `CreationPage` or nested components under `features/creation/workflow`.

## Migration Strategy

Because the user selected "full copy yuetools", the implementation plan should cover all target domains, but it should land in controlled slices:

1. Backend foundation: SQLAlchemy models, migration/bootstrap, error envelope, auth dependencies.
2. Auth/profile: RSA key flow, Argon2id password storage, login/register/logout/me/profile/avatar.
3. Credits/usage: accounts, ledger, grants, reservation guard, daily counters.
4. Song assets: save/list/detail/update/delete and Creation output save.
5. Product shell: router, AppShell, login/register/settings/profile, global credit/quota state.
6. Music: player store/page, playlist sync, local import upload/stream.
7. Creation integration: auth gate, quota/credit guard, asset save, advanced workflow/debug UI placement.
8. Image/audio placeholders: explicit target tabs and explicit not-implemented generation endpoints.

Each slice should include tests and should leave the app runnable.

## Testing

Backend:

- Auth key issue/decrypt success.
- Register stores Argon2id hash, never plaintext.
- Login succeeds/fails correctly.
- Profile update/avatar upload.
- Credit grants idempotency.
- Reserve/capture/release state transitions.
- Quota exhausted blocks lyrics/image/audio scene.
- Creation success captures; failure releases.
- Song asset ownership checks.
- Music local import owner checks.

Frontend:

- Router guards redirect unauthenticated users.
- Shell defaults to Music.
- Login/register encrypt passwords before sending.
- Profile form persists all required fields.
- Assets Song Inspiration displays clue/title/style/lyric.
- Creation page can save result to assets.
- Quota chips render exhausted state.
- Music page empty state, queue state, and import controls render.

End-to-end smoke:

- Register -> login/me -> update profile -> run lyrics creation -> save asset -> see asset -> open Music.

## Acceptance Criteria

- Opening the app lands on Music.
- Unauthenticated cloud user is sent to login for protected pages.
- User can register/login/logout.
- Profile fields are editable: gender, birthday, bio, nickname, avatar.
- Passwords are encrypted in transit and Argon2id-hashed at rest.
- Credits and daily quotas are visible.
- Lyrics generation is limited to 100 admitted attempts per day.
- Image and audio-effect quotas are visible and their generation endpoints fail explicitly until implemented.
- Credits use reserve/capture/release for generation scenes.
- Assets tab has working Song Inspiration records with clue/title/style prompt/lyric.
- Existing Pro lyrics workflow remains available under Creation.
- Workflow trace/debug surfaces are secondary controls, not the main product experience.
- Music tab is the default player interface.
