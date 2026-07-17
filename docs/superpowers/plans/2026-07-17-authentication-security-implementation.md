# Authentication Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current long-lived localStorage bearer login with refreshable, device-bound sessions and close authentication, authorization, rate-limit, and logging gaps.

**Architecture:** FastAPI issues 30-minute PyJWT access tokens and opaque rotating refresh credentials backed by `UserSession`. Web credentials use HttpOnly cookies while access tokens remain in Pinia memory. Shared authentication dependencies enforce token, database session, device, Origin, and resource-owner invariants before protected work executes.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy asyncio, PyJWT, argon2-cffi, cryptography, Vue 3, Pinia, Node test runner, pytest.

## Global Constraints

- Follow `/Users/bytedance/Documents/projects/yts/docs/superpowers/specs/2026-07-17-authentication-security-design.md`.
- Access tokens last 30 minutes and refresh begins five minutes before expiry.
- Refresh sessions slide for 30 days and have a 90-day absolute limit.
- Email ownership verification is deferred; no code or response may claim an email is verified.
- Cloud authentication and authorization failures must stop the control flow; no fallback to anonymous execution.
- Do not persist access or refresh credentials in localStorage or sessionStorage.
- Preserve unrelated worktree changes.

---

### Task 1: Strict Security Configuration

**Files:**
- Modify: `core/yts_core/config.py`
- Modify: `conf/cloud.env`
- Modify: `conf/local.env`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `AuthSettings` properties for key ring, issuer, audience, token/session TTLs, cookie mode, worker count, trusted proxies, and limiter mode.
- Consumes: existing `Settings` profile loading and legacy environment mapping.

- [ ] **Step 1: Write failing tests** asserting cloud configuration rejects the source default signing key, multi-worker in-memory limiting, and insecure production cookies, while the local profile accepts explicit development settings.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_settings.py -k 'auth or security or worker or cookie'` and verify the new assertions fail for the missing fields and validators.
- [ ] **Step 3: Implement focused auth configuration** with explicit fields: `jwt_keys`, `jwt_active_kid`, `issuer`, `audience`, `access_token_ttl_seconds=1800`, `refresh_sliding_ttl_seconds=2592000`, `refresh_absolute_ttl_seconds=7776000`, `cookie_secure`, `cookie_domain`, `worker_count`, `rate_limit_backend`, and `trusted_proxies`. Validate that cloud settings contain a non-default active key, secure cookies for production mode, and one worker for the in-memory limiter.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests/test_settings.py` and verify all settings tests pass.
- [ ] **Step 5: Commit** `core/yts_core/config.py`, the two ignored local templates only if intentionally force-added already, and `tests/test_settings.py` with message `feat: enforce authentication security configuration`.

### Task 2: Password, Token, And Session Primitives

**Files:**
- Modify: `server/yts_server/security/passwords.py`
- Rewrite: `server/yts_server/security/tokens.py`
- Create: `server/yts_server/security/refresh_tokens.py`
- Modify: `server/yts_server/db/models.py`
- Create: `server/yts_server/alembic/versions/20260717_01_device_sessions.py`
- Test: `tests/test_auth_security_primitives.py`

**Interfaces:**
- Produces: `verify_and_update_password(password, digest) -> tuple[bool, str | None]`.
- Produces: `issue_access_token(settings, session_record) -> AccessToken` and `decode_access_token(settings, token) -> AccessClaims`.
- Produces: opaque refresh generation, SHA-256 digesting, and constant-time verification helpers.
- Produces: a device-bound `UserSession` schema with string UUID primary key.

- [ ] **Step 1: Write failing primitive tests** for Argon2 rehash, required JWT claims, `kid` selection, wrong issuer/audience/type, missing claims, random IDs, refresh digest verification, and model field constraints.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_auth_security_primitives.py` and verify failures identify the missing APIs and claims.
- [ ] **Step 3: Implement primitives** using `PasswordHasher.check_needs_rehash`, PyJWT fixed `HS256`, `jwt.get_unverified_header` only to select a configured `kid`, a typed `AccessClaims` dataclass, `secrets.token_urlsafe(48)` refresh values, `hashlib.sha256`, and `hmac.compare_digest`.
- [ ] **Step 4: Replace `UserSession` fields** with random string `id`, `user_id` foreign key, user/device identity, refresh digest/generation, expiry/activity/revocation/risk metadata, and add the migration that transforms or invalidates existing sessions explicitly.
- [ ] **Step 5: Run** `.venv/bin/python -m pytest -q tests/test_auth_security_primitives.py tests/test_auth_profile_routes.py` and verify primitives pass while route failures are limited to the intentional old contract.
- [ ] **Step 6: Commit** with message `feat: add device-bound authentication primitives`.

### Task 3: Bounded Rate Limiting And Password-Key Cache

**Files:**
- Create: `server/yts_server/security/rate_limits.py`
- Modify: `server/yts_server/security/password_keys.py`
- Modify: `server/yts_server/errors.py`
- Test: `tests/test_auth_rate_limits.py`

**Interfaces:**
- Produces: `SlidingWindowLimiter.check(bucket, key, limit, window_seconds) -> None` raising an explicit HTTP 429 `AppError`.
- Produces: `issue_password_key()` with a hard cache limit and observable rejection.

- [ ] **Step 1: Write failing tests** using a controllable monotonic clock for first-N acceptance, N+1 rejection, window expiry, bounded bucket/key counts, and RSA cache capacity before key generation.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_auth_rate_limits.py` and verify the tests fail because the limiter and capacity behavior do not exist.
- [ ] **Step 3: Implement a locked bounded limiter** storing deques by `(bucket, key)` with hard key capacity and explicit eviction of expired empty keys. Add `AppError.too_many_requests` with a stable public code.
- [ ] **Step 4: Enforce RSA cache capacity** under the existing lock before calling `rsa.generate_private_key`; do not evict a live private key silently.
- [ ] **Step 5: Run** `.venv/bin/python -m pytest -q tests/test_auth_rate_limits.py` and verify all boundary tests pass.
- [ ] **Step 6: Commit** with message `feat: bound authentication key and rate-limit state`.

### Task 4: Registration, Login, Refresh, And Logout Routes

**Files:**
- Rewrite: `server/yts_server/domains/auth.py`
- Modify: `server/yts_server/routes/auth.py`
- Modify: `server/yts_server/routes/dependencies.py`
- Create: `server/yts_server/security/request_context.py`
- Test: `tests/test_auth_profile_routes.py`
- Create: `tests/test_auth_refresh_routes.py`

**Interfaces:**
- Produces: registration/login handlers accepting FastAPI `Request`/`Response` to set device and refresh cookies.
- Produces: `POST /api/auth/refresh` with `X-Refresh-Request-ID` and rotating credentials.
- Produces: `authenticate_bearer_token(session, token, device_id)` enforcing claim/session identity.
- Produces: `optional_current_user` that is anonymous only when no credential is presented in an explicitly local route.

- [ ] **Step 1: Add failing route tests** for case-folded email uniqueness, non-enumerating availability/registration, password rehash, cookie attributes, required device cookie, user/session mismatch, refresh success, expiry, logout revocation, and missing/invalid credential behavior.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_auth_profile_routes.py tests/test_auth_refresh_routes.py` and confirm each new security assertion fails on the old routes.
- [ ] **Step 3: Implement request context extraction** from server headers and trusted proxies, generating the device cookie only at registration/login/refresh boundaries.
- [ ] **Step 4: Implement transactional registration/login** with normalized email, database conflict mapping, Argon2 rehash, random Session creation, access response, and refresh/device HttpOnly cookies.
- [ ] **Step 5: Implement refresh rotation** with refresh digest checking, expiry/replay revocation, generation increment, bounded 60-second idempotency records, and identical replay response for the same request ID.
- [ ] **Step 6: Implement logout** to revoke the Session and clear both cookies even when the response completes successfully; invalid authentication still fails explicitly.
- [ ] **Step 7: Run** `.venv/bin/python -m pytest -q tests/test_auth_profile_routes.py tests/test_auth_refresh_routes.py` and verify all route tests pass.
- [ ] **Step 8: Commit** with message `feat: add refreshable device login sessions`.

### Task 5: Logging Redaction

**Files:**
- Modify: `server/yts_server/errors.py`
- Test: `tests/test_auth_profile_routes.py`
- Test: `tests/test_structured_logging.py`

**Interfaces:**
- Produces: validation logs containing path, method, request ID, and invalid field names without body bytes.

- [ ] **Step 1: Write a failing log-capture test** submitting an invalid login payload containing unique token, ciphertext, and password markers and asserting none appear in logs.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_auth_profile_routes.py -k validation_log` and verify the marker currently leaks.
- [ ] **Step 3: Remove request-body reads and decoding** from the validation handler; log only safe structural fields and request correlation ID.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests/test_auth_profile_routes.py tests/test_structured_logging.py` and verify redaction and logging contracts pass.
- [ ] **Step 5: Commit** with message `fix: redact authentication validation logs`.

### Task 6: Protected HTTP And WebSocket Authorization

**Files:**
- Modify: `server/yts_server/routes/billing_guard.py`
- Modify: `server/yts_server/routes/image.py`
- Modify: `server/yts_server/routes/music_stream.py`
- Modify: `server/yts_server/routes/workflow.py`
- Modify: `server/yts_server/domains/workflow_history.py`
- Modify: `core/yts_core/orchestration/checkpointing.py`
- Test: `tests/test_creation_billing_integration.py`
- Test: `tests/test_workflow_routes.py`
- Create: `tests/test_protected_stream_routes.py`

**Interfaces:**
- Produces: cloud-required/local-optional authentication that rejects every presented invalid credential.
- Produces: Origin-validated WebSocket authentication before expensive work.
- Produces: workflow ownership records checked before resume, trace, and streaming operations.

- [ ] **Step 1: Write failing integration tests** proving anonymous cloud image/music/workflow calls are rejected, invalid local credentials do not become anonymous, disallowed WebSocket Origins are rejected before accept, and one user cannot resume or trace another user's thread.
- [ ] **Step 2: Run the focused tests** and verify they expose the current anonymous and ownership gaps.
- [ ] **Step 3: Centralize cloud-required/local-optional authentication** and pass the authenticated user into `GenerationBillingGuard`; wire image and music generation through it.
- [ ] **Step 4: Add WebSocket Origin and initial-message token checks** before model/checkpoint operations. Bound prompt length, duration, and message size at the protocol model boundary.
- [ ] **Step 5: Persist and verify workflow ownership** before checkpoint resume/trace; key new checkpoint namespaces by user and refuse legacy ownerless cloud checkpoints.
- [ ] **Step 6: Run** `.venv/bin/python -m pytest -q tests/test_creation_billing_integration.py tests/test_workflow_routes.py tests/test_protected_stream_routes.py` and verify all authorization tests pass.
- [ ] **Step 7: Commit** with message `fix: enforce generation and workflow authorization`.

### Task 7: Frontend In-Memory Session And Weak-Network Refresh

**Files:**
- Create: `desktop/frontend/src/services/sessionRefresh.js`
- Modify: `desktop/frontend/src/services/auth.js`
- Modify: `desktop/frontend/src/services/transport.js`
- Modify: `desktop/frontend/src/stores/auth.js`
- Modify: `desktop/frontend/src/router/index.js`
- Modify: `desktop/frontend/src/main.js`
- Create: `desktop/frontend/tests/sessionRefresh.test.js`
- Modify: `desktop/frontend/package.json`
- Test: `tests/test_frontend_creator_os_layout.py`

**Interfaces:**
- Produces: `createSessionRefresher({ refresh, now, schedule })` with single-flight, five-minute early scheduling, bounded network retry, and explicit invalid-session clearing.
- Produces: credentialed HTTP/WebSocket transport reading access tokens from an injected memory getter.

- [ ] **Step 1: Add Node failing tests** for single-flight concurrency, early scheduling, timeout retaining state, expired-token request blocking, and explicit 401 clearing state. Add Python source-contract assertions forbidding credential keys in Web Storage.
- [ ] **Step 2: Run** `node --test desktop/frontend/tests/sessionRefresh.test.js` and the focused Python frontend test; verify failures reflect the missing refresher and current localStorage token usage.
- [ ] **Step 3: Implement the pure refresh state machine** without Vue dependencies, using one active promise and bounded retry delays.
- [ ] **Step 4: Rewrite the Pinia auth store** so tokens exist only in memory, hydration calls refresh, timers are cancelled on logout, and network errors preserve user state while invalid-session errors clear it.
- [ ] **Step 5: Inject memory token access into transport**, use `credentials: "include"`, attach refresh request IDs, refresh once on an expired 401, and never put credentials in URLs.
- [ ] **Step 6: Update router startup** to await hydration before protected navigation and remove token-based guest decisions from localStorage.
- [ ] **Step 7: Run** `node --test desktop/frontend/tests/sessionRefresh.test.js`, `.venv/bin/python -m pytest -q tests/test_frontend_creator_os_layout.py`, and `npm --prefix desktop/frontend run build`.
- [ ] **Step 8: Commit** with message `feat: add weak-network resilient frontend sessions`.

### Task 8: Full Verification And Security Review

**Files:**
- Modify only files required by verified failures.

**Interfaces:**
- Consumes every prior task's public contract.
- Produces a clean, evidence-backed final state.

- [ ] **Step 1: Run auth/security tests** with `.venv/bin/python -m pytest -q tests/test_auth_security_primitives.py tests/test_auth_rate_limits.py tests/test_auth_profile_routes.py tests/test_auth_refresh_routes.py tests/test_protected_stream_routes.py`.
- [ ] **Step 2: Run the full backend suite** with `.venv/bin/python -m pytest -q`.
- [ ] **Step 3: Run frontend verification** with `node --test desktop/frontend/tests/sessionRefresh.test.js` and `npm --prefix desktop/frontend run build`.
- [ ] **Step 4: Run lint and diff checks** with `.venv/bin/python -m ruff check core server tests`, `.venv/bin/python -m ruff format --check core server tests`, and `git diff --check`.
- [ ] **Step 5: Review the complete control flow** registration -> login -> refresh -> authenticated HTTP/WebSocket -> logout, including every failure branch and database mutation. Fix only demonstrated defects with a new failing test first.
- [ ] **Step 6: Confirm no secret/token persistence or logging** by reviewing the complete relevant files and running the targeted leak tests.
- [ ] **Step 7: Commit verified corrections** with message `test: verify authentication security flows` only if corrections were necessary.
