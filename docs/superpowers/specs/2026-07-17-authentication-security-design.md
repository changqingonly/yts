# Authentication Security Design

## Scope

This change hardens the existing registration, login, session, token, and protected-resource
flows for the Web and Tauri clients. It keeps Argon2id password storage and PyJWT signing,
adds refreshable device sessions, closes authentication and ownership gaps, and makes cloud
security configuration fail explicitly when incomplete.

Email ownership verification is intentionally out of scope for this internal-development
phase. Email normalization, uniqueness, and anti-enumeration remain in scope. Production
release must not be described as having verified email ownership until a real delivery and
verification flow is implemented.

## Security Invariants

- Passwords are stored only as Argon2id hashes. Successful login upgrades hashes whose
  parameters no longer match the configured hasher.
- Cloud authentication never starts with a source-code default signing secret.
- Every accepted access token is bound to one non-revoked database session and the same user
  and device recorded by that session.
- Authentication failure stops the protected control flow. Local-development exemptions are
  explicit profile behavior, not silent fallback from failed cloud authentication.
- Network failure is distinct from invalid credentials. A timeout never clears a valid local
  login state; an explicit invalid or revoked session does.
- Expensive generation, streaming, workflow mutation, history, and trace operations are
  authenticated and authorized in the cloud profile.
- Authentication request bodies, credentials, tokens, and password ciphertext are never
  written to logs.

## Password And Registration Flow

Registration continues to fetch a five-minute, one-use RSA-OAEP public key and sends encrypted
password fields. TLS remains mandatory for production; RSA-OAEP is protocol compatibility and
is not treated as a TLS replacement.

The password-key cache has a hard capacity and key issuance is rate limited before RSA key
generation. Cache exhaustion and rate-limit exhaustion return explicit errors. Multi-process
cloud deployment must use a shared password-key and rate-limit backend or configure sticky
routing; cloud startup must reject an unsupported multi-process configuration rather than
allow intermittent decrypt failures.

Email values are stripped and case-folded before lookup and storage. Registration and email
availability checks return non-enumerating responses. A database uniqueness conflict is mapped
to the same public registration response instead of leaking account existence or returning an
internal error. Email ownership is not asserted.

Login uses a uniform public error for unknown accounts and incorrect passwords. Login success
checks `PasswordHasher.check_needs_rehash()` and replaces an outdated hash in the same
transaction that creates the session.

## Token And Device Session Model

The access token lifetime is 30 minutes. Refresh begins five minutes before expiry. Refresh
sessions have a 30-day sliding lifetime and a 90-day absolute lifetime.

Access tokens contain and require:

- `iss` and `aud` identifying this service and client contract;
- `sub` for user UUID and `uid` for database user ID;
- `sid` for a random session UUID;
- `did` for the random device ID;
- `iat`, `nbf`, and `exp` timestamps;
- `jti` as a random token identifier;
- `typ=access`.

PyJWT decode fixes the accepted algorithm to HS256 and explicitly requires every claim. The
database session must match `sid`, `sub`, `uid`, and `did`, must not be revoked, and must be
inside both sliding and absolute expiry.

`UserSession` stores the session UUID, user ID and UUID, device ID, refresh-token SHA-256
digest, refresh generation, sliding and absolute expiration, creation and activity timestamps,
revocation timestamp and reason, client type, display name, application version, server-read
User-Agent, and server-observed IP address. User and session relationships use database foreign
keys.

The Web client receives the device ID and refresh credential only in HttpOnly cookies. In
production those cookies are `Secure` and `SameSite=Lax`; cloud production requires HTTPS.
Internal HTTP development uses explicit non-Secure development-cookie configuration. Tauri
Keychain integration is a later platform task; until then the desktop development client uses
the same loopback HttpOnly-cookie flow and does not persist bearer tokens in Web Storage.

Access tokens live in Pinia memory only. A page reload calls the refresh endpoint using the
HttpOnly cookie and reconstructs the in-memory session. No token is written to localStorage or
sessionStorage.

## Refresh And Weak-Network Semantics

The client schedules refresh five minutes before access-token expiry. All callers share one
single-flight refresh promise. While refresh is in flight, the existing access token remains
usable until its actual expiry.

Refresh rotation uses a client-generated request ID. The server records a short-lived,
encrypted idempotency result for the session and request ID for 60 seconds. Repeating the same
request returns the same rotation result and cookies. Reusing an older refresh credential with
a different request ID is a replay event and revokes the session.

Network timeout keeps the in-memory user state and retries with bounded exponential delays.
Once the access token has expired, new protected requests wait for refresh. If refresh still
cannot reach the server, they fail explicitly with a network/session-unavailable error; they do
not execute anonymously. An explicit invalid, expired, replayed, or revoked refresh response
clears the client session.

An authenticated WebSocket is checked when it is established. An established music stream is
not disconnected solely because its access token later expires. Reconnection obtains a current
access token first.

## Environment And Risk Signals

The server generates the stable random device ID. JavaScript cannot read it. The session also
records client type, display name, application version, User-Agent, IP address, creation time,
last-seen time, last-refresh time, revocation time, and revocation reason.

Session/user/device mismatches are hard authentication failures. IP and normal User-Agent
changes are audit and risk signals, not hard failures, because mobile networks, weak networks,
and browser upgrades change them legitimately. Refresh replay, incompatible client-type
changes, and concurrent geographically implausible use are explicit risk events. Advanced
geolocation scoring is outside this implementation, but the stored facts support it.

The server trusts forwarding headers only when the request came through configured trusted
proxies. It never accepts a client-supplied IP address from a JSON body. Browser fingerprinting
such as Canvas, fonts, or hardware identifiers is not collected.

## Rate Limiting

Login, registration, email checks, password-key issuance, refresh, and authentication-sensitive
WebSocket establishment use bounded sliding-window limits. Limits combine appropriate keys,
including source IP, normalized account hash, session, and device. Responses use HTTP 429 and
do not reveal whether an account exists.

The first implementation uses a bounded in-process limiter for the supported single-process
development deployment. Cloud configuration declares the worker count and rejects more than
one worker until a shared limiter is configured. This exposes the deployment constraint rather
than presenting per-process limits as global protection.

## Protected Resource Authorization

Cloud routes for image generation, music streaming, workflow run, resume, history, trace, and
streaming require an authenticated user. Generation routes enter the existing billing guard.
Workflow checkpoints and history are keyed or indexed by user UUID, workflow ID, and thread ID.
Every resume and trace read verifies ownership before accessing checkpoint data.

WebSocket endpoints validate the configured Origin before accepting the connection. Tokens are
accepted through the initial protocol message where browser WebSocket headers cannot supply an
Authorization header; credentials are never put in URLs or logs.

The local profile may run generation without an account only where explicitly documented for
offline desktop operation. A presented but invalid credential always fails; it never falls back
to anonymous local execution.

## Configuration

Cloud production requires explicit values for JWT secret, issuer, audience, HTTPS cookie mode,
allowed origins, trusted proxies, worker count, and rate-limit mode. Missing or incompatible
values fail application startup. Local development defaults are isolated to the local profile.

Signing-key rotation is represented by a `kid` and a configured key ring. One key signs new
tokens; active and retiring keys verify existing tokens until their maximum lifetime passes.
Secrets are supplied outside Git-tracked source files.

## Logging And Errors

Validation-error logs contain method, path, request correlation ID, and invalid field names
only. They never contain request bodies. Authentication logs contain event type, session ID,
hashed account identifier, device ID, outcome, and server-observed risk metadata without token,
password, ciphertext, cookie, or Authorization values.

Client-visible errors distinguish validation, rate limiting, invalid credentials, revoked
sessions, refresh replay, authorization failure, and temporary network failure without exposing
internal exceptions or account existence.

## Testing

Tests are written before each behavior and must demonstrate failure before implementation.
Coverage includes:

- Argon2id storage, mismatch, and successful rehash upgrade;
- required JWT claims, fixed algorithm, issuer/audience, token type, expiry, and key ID;
- session user/device binding and revocation;
- refresh success, rotation, same-request idempotency, replay revocation, expiry, and concurrent
  single-flight behavior;
- weak-network timeout without logout and explicit invalid-session logout;
- normalized email uniqueness and non-enumerating responses;
- limiter boundaries, bounded RSA cache, and unsupported multi-worker startup failure;
- anonymous generation rejection, billing entry, WebSocket Origin rejection, and cross-user
  workflow run/resume/trace rejection;
- validation-log redaction;
- absence of credential persistence in Web Storage;
- explicit cloud configuration failures and local-profile behavior.

The focused authentication suite, frontend tests, lint checks, and full repository test suite
must pass before completion.

## Deferred Production Requirement

Before public launch, implement real email ownership verification with a configured delivery
provider, expiring single-use verification records, resend limits, and verified-state gates for
the required product operations. Until that work exists, product and API responses must not
claim that an email address is verified.
