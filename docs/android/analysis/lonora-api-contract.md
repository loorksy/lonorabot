# Lonora backend: client-facing API contract for a native Android (Flutter) client

Status: analysis, written from the repository as checked out (API `FastAPI title="Lonora" version="0.2.0"`).
Scope: every HTTP route, WebSocket and SSE channel a native client can reach, with auth, shapes,
errors, idempotency, pagination, realtime protocol, push, updates, voice and safety notes.

## 0. Legend and conventions

Evidence labels:

- **VERIFIED**: read in code; citation `file:line` follows.
- **INFERRED**: follows from code or library defaults, not stated outright.
- **UNKNOWN**: not determinable from the repository.

Path abbreviations used in citations:

| Prefix | Means |
|---|---|
| `A/` | `apps/api/src/lonora_api/` |
| `R/` | `apps/api/src/lonora_api/routes/` |
| `W/` | `apps/api/src/lonora_api/websocket/` |
| `C/` | `packages/contracts/src/lonora_contracts/` (Python contracts, the source of truth) |
| `T/` | `packages/contracts/src/` (TypeScript mirrors) |
| `D/` | `packages/db/src/lonora_db/` |
| `M/` | `apps/mobile/lib/` (the existing Expo client) |

All `/api/*` routes are mounted by `A/app.py:128-133` (`prefix="/api"`), in the order of the `ROUTES`
tuple at `A/app.py:22-80`. WebSockets `events`, `market`, `voice` are mounted under `/api` too
(`A/app.py:131-133`). `/health` and `/ready` are mounted at the root, **not** under `/api`
(`A/app.py:127`).

Every JSON contract model uses `extra="forbid"` (`C/domain.py:16-17`): **unknown request fields are
rejected with 422**. A Flutter client must not send extra keys (for example a `client_version` field).

---

## 1. Global HTTP conventions

### 1.1 Error envelope

| Source | Status | Body | Evidence |
|---|---|---|---|
| Domain error (`LonoraError`) | as raised | `{"code": "<snake_code>", "request_id": "<id>"}` | VERIFIED `A/errors.py:13-17` |
| Request body/query validation | 422 | `{"code": "invalid_request" \| <policy code>, "fields": [{"path": [...], "code": "<pydantic type>"}]}` | VERIFIED `A/errors.py:20-31` |
| DB integrity conflict | 409 | `{"code": "resource_conflict"}` | VERIFIED `A/errors.py:34-36` |
| Pydantic error raised inside a handler | 422 | `{"code": "invalid_request" \| <policy code>}` | VERIFIED `A/errors.py:38-40` |
| Starlette HTTP error | as raised | `{"code": "endpoint_not_found"}` (404) or `{"code": "request_failed"}` | VERIFIED `A/errors.py:42-47` |
| Rate limit | 429 | `{"code": "rate_limited"}` + `Retry-After: 60` | VERIFIED `A/middleware/rate_limit.py:40` |
| Body too large | 413 | `{"code": "request_body_too_large"}` | VERIFIED `A/http_body.py:20,31` |
| Proxy maintenance (Caddy, during update/rollback) | 503 | `{"error": "maintenance", "message": "..."}` + `Retry-After: 120`, only for non-GET/HEAD/OPTIONS | VERIFIED `infra/compose/Caddyfile.prod` (`@maintenance` block) |

Important consequences:

- A body that fails a `model_validator` (for example `message_content_required`, `voice_note_invalid`,
  `one_schedule_required`) does **not** surface that string as `code`; the client sees
  `code: "invalid_request"` and `fields[].code = "value_error"`. The only validator messages promoted
  to `code` are the reach-me policy codes in `POLICY_ERROR_CODES` (`incoming_call_channel_conflict`,
  `incoming_call_device_required`, `incoming_call_quiet_hours_incomplete`,
  `incoming_call_quiet_hours_empty`, `invalid_timezone`). VERIFIED `C/incoming_calls.py:21-38`,
  `A/errors.py:20-31`. Exception: `PUT /api/routines/{id}` converts its merged-validation error
  message to `code` explicitly (VERIFIED `R/routines.py` `update`, lines 43-56).
- The maintenance 503 body has `error`, not `code`. The Expo client treats every 503 as "the API
  answered" (VERIFIED `M/outgoing-messages.ts:20-30`), so a send is marked failed, not queued.
- A bare 502/504 with no Lonora `code` means "the API never saw it" (Expo rule, same file).

### 1.2 Request id, security headers, timing

- `X-Request-Id`: client may supply `[a-zA-Z0-9_-]{8,64}`; otherwise a UUID is generated; always echoed.
  VERIFIED `A/middleware/request_id.py:15,20`.
- `Server-Timing` (`api`, `auth`, `message_db`) only on `POST /api/threads/{id}/messages`. VERIFIED
  `A/middleware/request_id.py:23-31`.
- Responses carry `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.

### 1.3 Body limits

- Every POST/PUT/PATCH body is buffered and capped at **20 MiB** (`20*1024*1024`), checked against
  `Content-Length` and the streamed size. VERIFIED `A/http_body.py:9-31`.
- Uploaded files are capped at 20 MiB too (`MAX_ATTACHMENT_BYTES`). VERIFIED
  `packages/core/src/lonora_core/attachments.py`. Because the whole multipart body is also capped at
  20 MiB, the effective maximum file size is 20 MiB minus multipart framing. INFERRED.

### 1.4 CORS

`allow_origins=[LONORA_ALLOWED_ORIGIN]`, credentials allowed, headers `Content-Type, X-CSRF-Token,
Authorization, X-Request-Id`; exposes `X-Request-Id, Server-Timing`. VERIFIED `A/app.py:115-122`.
Irrelevant for a native client (no browser CORS), but see the WebSocket `Origin` rule in section 4.

### 1.5 Rate limits

| Bucket | Routes (POST only) | Default | Evidence |
|---|---|---|---|
| `password` (shared) | `/api/auth/login`, `/api/auth/mobile/login`, `/api/onboarding` | 10 / minute / client host | VERIFIED `A/middleware/rate_limit.py:12-17,35`; `A/env.py:19` (`auth_rate_limit_per_minute`, 1..100000) |
| `enrollment` | `/api/auth/devices/enrollment` | same limit | VERIFIED same |
| `enrollment_verify` | `/api/auth/devices/enrollment/verify` | same limit | VERIFIED same |

- The key is `request.client.host`. Uvicorn is started without `forwarded_allow_ips`
  (VERIFIED `A/server.py` `serve`), so its default `FORWARDED_ALLOW_IPS="127.0.0.1,::1"` applies
  (VERIFIED in installed `uvicorn/config.py:361-363`). In production the API sits behind Caddy in
  another container, so all clients probably share **one** bucket keyed by Caddy's address. INFERRED.
  A Flutter client must handle 429 with `Retry-After: 60` on login gracefully.
- Other routes have no rate limit at the HTTP layer (some domain limits exist: passkey challenges
  `device_challenge_limit` 429 at 8 pending, VERIFIED `packages/auth/src/lonora_auth/devices.py:88`;
  incoming calls `incoming_call_rate_limited` 429).

### 1.6 Idempotency and concurrency patterns (summary)

| Pattern | Where | Semantics | Evidence |
|---|---|---|---|
| `client_nonce` (1..80 chars, per thread) | `POST /api/threads/{id}/messages` | Same nonce in the same thread returns the original message, `deduplicated: true`; conflicts only for `ui_submit`/`input_answer` mismatches | VERIFIED `D/messages.py:335-396` |
| `client_nonce` (1..80) | `POST /api/voice/sessions`, `/api/voice/cancel-initialization` | One paid WebRTC intent per receipt | VERIFIED `C/voice.py:8-27`; `docs/GPT_LIVE.md` |
| `operation_id` | `POST /api/trading/execute` (`TradeRequest`) | Executor answers a repeated id from its journal | VERIFIED `C/trading.py:28-31`; `docs/trading-safety.md` ("Owner close and cancel keep one operation id") |
| `version` (optimistic) | generic resources `PUT /api/<resource>/{id}` body `{version, payload}` | `409 version_conflict` when stale | VERIFIED `D/transactions.py:197` |
| `expected_version` | tasks control/complete, artifact text, skill restore | `409 version_conflict` | VERIFIED `C/tasks.py:88-98`, `R/artifacts.py:137-138` |
| `expected_revision` / `expected_scope_revision` | agent model, skill revocations, agent scope change | stale → 409 | VERIFIED `C/model_routing.py:90-93`, `C/skills.py:43-45`, `C/domain.py:45` |
| Idempotent decision | owner-action decision, trade approval decision | repeating the same decision answers from the record | VERIFIED `R/owner_actions.py:182-187` |
| Run retry | `POST /api/runs/{id}/retry` | idempotent per failed run | VERIFIED `R/runs.py:66-80` (docstring) |

---

## 2. Authentication and session

### 2.1 Two credential modes, one dependency

Every protected route depends on `require_owner` (188 uses, no other auth dependency exists;
VERIFIED by grep over `R/` and `W/`). It reads `Authorization: Bearer <token>` first, then the
`lonora_session` cookie (VERIFIED `A/middleware/auth.py:16-20`).

- **Bearer** (native): CSRF is **not** checked. VERIFIED `A/middleware/auth.py:23`.
- **Cookie** (browser): for every method other than GET/HEAD/OPTIONS the `X-CSRF-Token` header must
  match the session's CSRF hash, else `403 csrf_required`. VERIFIED `A/middleware/auth.py:23-24`,
  `packages/auth/src/lonora_auth/sessions.py:49-56`.

**Which routes accept Bearer?** Every route that requires an owner (all of section 3's "Owner" rows,
plus SSE `/api/events/stream`). WebSockets do not read the header; they take the token in the first
frame (section 4). VERIFIED.

Side effect of every authenticated call: `ensure_personal_agent` runs, so the owner's personal agent
always exists. VERIFIED `A/middleware/auth.py:25`.

### 2.2 Token properties

| Property | Value | Evidence |
|---|---|---|
| Format | `secrets.token_urlsafe(48)` (64 URL-safe chars) | VERIFIED `packages/auth/src/lonora_auth/sessions.py:19` |
| Storage server-side | SHA-256 hash in `SessionRow`, plus CSRF hash | VERIFIED same file, lines 14-28 |
| Lifetime | absolute, `LONORA_SESSION_SECONDS`, default **86400 s (1 day)**, allowed 300..2592000 | VERIFIED `A/env.py:15`; `docs/operations.md:639` |
| Refresh / sliding renewal | **none**; expiry is fixed at issue, and no refresh route exists | VERIFIED `sessions.py:18-40`; route list of `R/auth.py` |
| Validity check | token exists, not revoked, not expired, owner exists, else `401 unauthorized` | VERIFIED `sessions.py:31-40` |

Decision-relevant: with the default config the native user is logged out every 24 h. The client must
keep the server URL and email and send the user to sign-in on any 401 (the Expo client does this:
VERIFIED `M/api.ts:82`, `M/session.tsx:79`). Raising `LONORA_SESSION_SECONDS` is an operator setting
(max 30 days).

### 2.3 Server URL selection

- The user types a server URL, normalized by stripping a trailing `/api` and `/`; must be http/https,
  no credentials, query or fragment. VERIFIED `M/api.ts:100-109`. Placeholder
  `https://lonora.example.com` (VERIFIED `apps/mobile/app/sign-in.tsx:166`).
- Deep link from Lonora Cloud: `lonora://connect?server=https://<handle>.<domain>[&token=<setup token>]`;
  remote servers must be https; http only for local/private addresses; token `[A-Za-z0-9_-]{20,128}`
  held in memory for that server only. VERIFIED `M/connect-link.ts:1-62`. (Server requires
  bootstrap tokens of >= 24 chars: VERIFIED `C/auth.py:13-14`.)
- Before showing sign-in vs first-run, the client calls `GET {server}/api/onboarding` and accepts only
  a boolean `owner_initialized` (anything else is "not a Lonora server"). VERIFIED `M/api.ts:113-123`.
- The URL scheme `lonora` and package `ai.lonora.mobile` come from `packages/ui-tokens/src/brand.ts:3-5`.
  A Flutter app with another package can still register the `lonora://` scheme. INFERRED.

### 2.4 Auth routes

| Method | Path | Auth | Request | Response | Errors | Evidence |
|---|---|---|---|---|---|---|
| GET | `/api/onboarding` | none | - | `{"owner_initialized": bool}` | 503 db | VERIFIED `R/onboarding.py:11-14` |
| POST | `/api/onboarding` | none, rate-limited (`password`) | `OnboardingRequest {email 3..254, password 1..128 (12..128 enforced on hashing), bootstrap_token 24..256}` | 201 `{"owner_initialized": true}` (no token) | 403 `invalid_bootstrap_token`, 409 `owner_already_initialized`, 422 `invalid_email`/`invalid_password` | VERIFIED `R/onboarding.py:17-23`, `C/auth.py:6-14`, `packages/auth/src/lonora_auth/owner_policy.py:13-26`, `account_security.py:17-27` (normalize_email 17, hash_password 24-26) |
| POST | `/api/auth/mobile/login` | none, rate-limited (`password`) | `LoginRequest {email, password}` | `{"owner": {"id","email"}, "token": "<bearer>", "expires_in": <seconds>}`; `Cache-Control: no-store`, `Pragma: no-cache` | 401 `unauthorized` (wrong email or password; constant-time dummy hash), 422, 429 | VERIFIED `R/auth.py:16-25,51-62` |
| POST | `/api/auth/login` | none (browser) | same | sets `lonora_session` (HttpOnly, SameSite=Strict) and `lonora_csrf` cookies; body `{"owner", "csrf"}` | same | VERIFIED `R/auth.py:28-48` (do not use from native) |
| GET | `/api/auth/session` | owner | - | `{"id", "email"}` | 401 | VERIFIED `R/auth.py:65-67` |
| POST | `/api/auth/logout` | owner | `{}` (body ignored) | `{"logged_out": true}`; revokes **this** session and deletes push devices registered by it | 401 | VERIFIED `R/auth.py:70-80` |

First-run flow (as the Expo app does it): `POST /api/onboarding`, treat `409 owner_already_initialized`
as success, then `POST /api/auth/mobile/login`. VERIFIED `M/session.tsx:137-141`. An operator can also
create the owner offline (`lonora-api --create-owner`), VERIFIED `A/server.py` `main`.

There is one owner per installation (`get_owner(session)` with no id). VERIFIED
`R/auth.py:19`, `owner_policy.py:16`.

### 2.5 Session revocation

- Only the current session can be revoked (`/api/auth/logout`). There is **no** route to list sessions,
  revoke other sessions or "sign out everywhere". VERIFIED (route enumeration of `R/auth.py`,
  `R/device_authority.py`).
- Open WebSockets and SSE streams re-check the token every 5 s and close on revocation/expiry
  (section 4). VERIFIED `W/events.py:36-39`, `R/events.py:18,68-76`.

### 2.6 Passkeys (WebAuthn) and step-up

Passkeys are "devices", never login. They are required for: enrolling a device, activating an account
authority (signed trading delegation), and as the `device_id` of the incoming-call policy.

| Method | Path | Request | Response | Errors / limits | Evidence |
|---|---|---|---|---|---|
| GET | `/api/auth/devices/config` | - | `{"rp_id", "android_configured": bool, "ios_configured": bool}` | `409 device_secure_origin_required` if origin not https (localhost http allowed) | VERIFIED `R/device_authority.py:21-28`, `packages/auth/src/lonora_auth/devices.py:36-50` |
| GET | `/api/auth/devices` | - | `[{"id","name","created_at"}]` | | VERIFIED `R/device_authority.py:31-37` |
| POST | `/api/auth/devices/enrollment` (rate-limited) | `DeviceEnrollment {password (re-auth), name 1..80}` | `{"challenge_id", "publicKey": <WebAuthn PublicKeyCredentialCreationOptions JSON>}` | 401 wrong password, 409 `device_limit` (16), 429 `device_challenge_limit` (8 pending); challenge TTL 120 s; ES256 only; UV required; resident key preferred | VERIFIED `devices.py:88,98,172-209`, `C/devices.py:10-17` |
| POST | `/api/auth/devices/enrollment/verify` (rate-limited) | `DeviceProof {challenge_id, credential: <RegistrationResponseJSON>}` (<= 64 KiB) | `{"id","name"}` | 403 `device_proof_invalid`, 404 `device_challenge_not_found`, 409 `device_challenge_expired_or_used`, 409 `device_already_registered_or_limit` | VERIFIED `devices.py:212-250` |
| DELETE | `/api/auth/devices/{device_id}` | - | `{"revoked": true}`; also revokes every active account authority signed with it and bumps permissions | 404 `device_not_found` | VERIFIED `R/device_authority.py:60-104` |

Android binding (critical for a new package):

- RP ID = hostname of `LONORA_ALLOWED_ORIGIN`. VERIFIED `devices.py:36-50`, `R/device_authority.py:26`.
- Accepted origins = the web origin plus `android:apk-key-hash:<base64url(sha256(signing cert))>` for
  each configured `LONORA_PASSKEY_ANDROID_FINGERPRINTS` entry. VERIFIED `A/device_metadata.py:10-14`,
  `devices.py:162,226`.
- `/.well-known/assetlinks.json` publishes **one** statement with **one** `package_name`
  (`LONORA_PASSKEY_ANDROID_PACKAGE`, default `ai.lonora.mobile`) and the fingerprint list, relations
  `handle_all_urls` and `get_login_creds`. VERIFIED `A/device_metadata.py:17-32`, `A/env.py:22`,
  `A/app.py:104-108`.
- Therefore a Flutter app `ai.lonora.android` can use passkeys only if the operator switches
  `LONORA_PASSKEY_ANDROID_PACKAGE` to it (dropping `ai.lonora.mobile`) and adds its signing-cert
  fingerprint; serving both packages at once needs a backend change to emit two statements.
  VERIFIED (single statement) + INFERRED (Credential Manager requires assetlinks to match package).
- The Expo client passes `publicKey` straight to `react-native-passkeys` `create`/`get` and posts the
  JSON result. VERIFIED `M/device-proof.native.ts:11-34`. A Flutter client needs a Credential Manager
  plugin producing the same WebAuthn JSON (`RegistrationResponseJSON`/`AuthenticationResponseJSON`). INFERRED.

What does **not** require step-up: owner-action decisions (`POST /api/owner-actions/{id}/challenge`
always answers `409 owner_action_passkey_not_needed`; VERIFIED `R/owner_actions.py:98-109`), trade
approvals, Mandate (trading mode) taps, secret-card saves, agent pause. They require only a valid owner
session. VERIFIED (`R/owner_actions.py`, `R/trading.py:196-217`).

---

## 3. Route inventory (every route), grouped

"Owner" = `require_owner` (Bearer accepted). "Mobile uses" = path literal found in `apps/mobile`
(VERIFIED by grep over `apps/mobile/{lib,app,components}`).

### 3.1 Public / unauthenticated

| Method | Path | Purpose | Evidence |
|---|---|---|---|
| GET | `/health` | `{"status":"ok"}` or `503 database_unavailable` | VERIFIED `A/health.py:41-48` |
| GET | `/ready` | `{"database": true, "gateway": {...,"ready": bool}, "push": "configured"\|"not_configured"}`; 503 when gateway not ready | VERIFIED `A/health.py:51-68` |
| GET | `/.well-known/assetlinks.json` | Android passkey binding | VERIFIED `A/app.py:104-108` |
| GET | `/.well-known/apple-app-site-association` | `{"webcredentials":{"apps":[...]}}` | VERIFIED `A/app.py:110-112` |
| GET, HEAD | `/download/lonora.apk` | the Expo APK; `404 android_release_unavailable`, `503 android_release_invalid` | VERIFIED `A/app.py:135-151` |
| GET | `/api/mobile/updates` | Expo Updates v1 manifest | VERIFIED `R/mobile_updates.py:54-122` |
| GET | `/api/mobile/updates/assets/{sha256}.{ext}` | immutable OTA asset | VERIFIED `R/mobile_updates.py:125-146` |
| GET | `/api/version` | `{"version": "0.2.0", "build": <web build id or null>}` (web build only) | VERIFIED `R/version.py:13,28-30` |
| GET/POST | `/api/onboarding` | first-run | section 2.4 |
| POST | `/api/auth/login`, `/api/auth/mobile/login` | sign-in | section 2.4 |
| POST | `/api/webhook` | server-to-server, HMAC `x-lonora-signature`; never from a client | VERIFIED `R/webhook.py:16-34` |
| GET | `/charts/render`, `/chart-runtime/{path}`, `/charting_library/{path}` | credential-free chart renderer shell (WebView) | VERIFIED `A/chart_renderer.py:42-52` |
| GET | `/{path}` | web SPA fallback; `api/*` misses → `404 endpoint_not_found` | VERIFIED `A/app.py:157-173` |

### 3.2 Owner routes, full list by router file

Line numbers are the decorator lines.

| File | Routes |
|---|---|
| `R/auth.py` | POST `/api/auth/login` (28), POST `/api/auth/mobile/login` (51), GET `/api/auth/session` (65), POST `/api/auth/logout` (70) |
| `R/device_authority.py` | GET `/api/auth/devices/config` (21), GET `/api/auth/devices` (31), POST `/api/auth/devices/enrollment` (40), POST `/api/auth/devices/enrollment/verify` (49), DELETE `/api/auth/devices/{id}` (60) |
| `R/push_devices.py` | PUT `/api/push/devices/{device_id}` (19), DELETE same (33) |
| `R/app_opens.py` | POST `/api/app-opens` (16), GET (25), DELETE (33) |
| `R/account_authority.py` | GET/POST `/api/agents/{id}/account-authorities` (21/37), POST `/api/account-authorities/{id}/challenge` (65), POST `/api/account-authorities/verify` (76), POST `/api/account-authorities/{id}/revoke` (93) |
| `R/agent_permissions.py` | GET `/api/agents/{id}/permissions` (16) |
| `R/agent_models.py` | GET/PUT `/api/agents/{id}/model` (26/34), GET `/api/agents/{id}/model/summary` (45) |
| `R/onboarding.py` | GET/POST `/api/onboarding` |
| `R/agent_delivery.py` | GET `/api/agents/notifications` (14), GET/PUT `/api/agents/{id}/notifications` (22/29) |
| `R/agents.py` | GET/POST `/api/agents` (47/57), GET/PATCH/DELETE `/api/agents/{id}` (77/95/119), POST `/api/agents/{id}/conversation` (87) |
| `R/agent_state.py` | GET `/api/agents/{id}/state` |
| `R/performance.py` | GET `/api/agents/{id}/performance?account_id=&symbol=` |
| `R/attention.py` | GET `/api/attention/view` (20), GET `/api/attention` (27), POST `/api/attention/seen` (51), GET/PUT `/api/attention/policy` (59/65) |
| `R/workspace_running.py` | GET `/api/workspace/running` (23), POST `/stop` (29), POST `/stop-all` (41) |
| `R/agent_secrets.py` | GET `/api/secrets` (10), DELETE `/api/secrets/{id}` (20) |
| `R/agent_skills.py` | resource router `/api/skills` + GET `/api/skills/{id}/versions` (124), POST `/api/skills/{id}/restore` (134), GET `/api/agents/{id}/skills/catalog?offset=&limit=` (186), GET `/api/agents/{id}/skills/catalog/{skill_id}` (206), GET/POST `/api/agents/{id}/skills/revocations` (219/227) |
| `R/threads.py` | GET `/api/threads/inbox` (41), POST `/api/threads/read-all` (49), POST `/api/threads/prefs` (57), GET/PUT `/api/threads/settings` (65/73), GET/POST `/api/threads` (81/89), GET/DELETE `/api/threads/{id}` (97/105), PUT `/api/threads/{id}/options` (130), POST `/api/threads/{id}/read` (142), PATCH `/api/threads/{id}/prefs` (153), POST `/api/threads/{id}/clear` (164) |
| `R/chat_lists.py` | GET/POST `/api/chat-lists`, PUT/DELETE `/api/chat-lists/{id}`, PUT `/api/chat-lists/{id}/members` |
| `R/messages.py` | GET `/api/threads/{id}/messages` (21), POST `/api/threads/{id}/messages/{mid}/ui-state/{part}/unlock` (53), PUT `/api/threads/{id}/messages/{mid}/reactions/{emoji}` (68), DELETE `/api/threads/{id}/messages/{mid}/reactions` (81), POST `/api/threads/{id}/messages` (92) |
| `R/runs.py` | GET/POST `/api/runs` (21/46), GET `/api/runs/{id}` (54), POST `/api/runs/{id}/retry` (66), POST `/api/runs/{id}/resume` (83) |
| `R/cancellation.py` | POST `/api/runs/{id}/cancel` (16) |
| `R/groups.py` | resource router `/api/groups` + POST `/api/groups/create` (17) |
| `R/peer_messages.py` | resource router `/api/peer-messages` |
| `R/routines.py` | GET `/api/routines?agent_id=` (19), POST `/api/routines/{agent_id}` (33), PUT/DELETE `/api/routines/{id}` (43/59), GET `/api/routines/{id}/history` (68) |
| `R/memory.py` | GET/PUT `/api/agents/{id}/memory`, GET `/api/agents/{id}/memory/revisions?limit=`, GET/PUT `/api/owner/profile`, GET/POST `/api/owner/profile/lines`, PUT `/api/owner/preferences`, GET `/api/owner/profile/revisions`, POST `/api/memory/revisions/{id}/revert`, GET/PUT `/api/memory/semantic/config`, POST `/api/agents/{id}/memory/semantic` |
| `R/knowledge.py` | GET `/api/agents/{id}/knowledge`, POST `/api/agents/{id}/knowledge/notes`, PUT/DELETE `/api/agents/{id}/knowledge/notes/{note_id}` |
| `R/agent_goals.py` | resource routers `/api/agent-goals`, `/api/knowledge-links` |
| `R/scratchpad.py` | resource router `/api/scratchpad` |
| `R/artifacts.py` | resource router `/api/artifacts` + POST `/api/artifacts/upload` (47), PUT `/api/artifacts/{id}/text` (116), GET `/api/artifacts/{id}/file?preview=` (172) |
| `R/boards.py` | resource router `/api/boards` |
| `R/tickets.py` | resource router `/api/tickets` + POST `/api/tickets/{id}/start` |
| `R/search.py` | GET `/api/search?q=&category=&limit=&offset=` |
| `R/connection_tests.py` | POST `/api/providers/{provider}/test` (46), POST `/api/mcp/test` (67), POST `/api/trading/connections/test` (91) |
| `R/mcp.py` | resource router `/api/mcp` |
| `R/integrations.py` | resource router `/api/integrations` + POST `/api/integrations/secrets` (74) |
| `R/trusted_sources.py` | GET/POST `/api/trusted-sources` (52/57), POST `/{id}/revoke` (68), POST `/{id}/restore` (79), POST `/mcp/{connection_id}/preview` (111), POST `/mcp/{connection_id}` (135) |
| `R/capabilities.py` | GET `/api/capabilities` |
| `R/providers.py` | GET `/api/providers` (25), PUT `/api/providers/{provider}/credential` (51), GET `/api/providers/{provider}/models` (67) |
| `R/model_router.py` | GET/PUT `/api/settings/models` (29/34), PUT `/api/settings/models/backups` (43), GET/PUT `/api/settings/models/context` (53/63) |
| `R/usage.py` | GET `/api/usage/summary`, `/agents`, `/series`, `/rank`, `/export.csv` |
| `R/voice.py` | POST `/api/voice/sessions` (24), DELETE `/api/voice/sessions/{id}` (33), POST `/{id}/transcript` (41), POST `/{id}/interrupt` (55), GET `/api/voice/status` (68), GET `/api/voice/sessions/{id}` (78), POST `/api/voice/cancel-initialization` (85) |
| `R/incoming_calls.py` | GET/PUT `/api/voice/incoming/policy` (24/30), GET `/api/voice/incoming` (39), POST `/api/voice/incoming/{id}/respond` (59) |
| `R/market.py` | GET `/api/market/instruments`, `/symbols`, `/instrument`, `/quote`, `/candles`, `/calendar` |
| `R/charts.py` | resource router `/api/charts` (catalog omits `state.scene`) + GET `/api/charts/{id}/scene` (15), POST `/api/charts/{id}/refresh` (24) |
| `R/trading.py` | GET/POST `/api/trading/connections` (37/47), DELETE `/api/trading/connections/{id}` (62), GET `/api/trading/accounts/{id}` (77), POST `/api/trading/connections/{id}/simulation` (87), POST `/api/trading/execute` (97), GET `/api/trading/journal` (109), GET `/api/trading/receipts?thread_id=` (123), GET `/api/trading/approvals?thread_id=` (137), POST `/api/trading/approvals/{id}/decision` (196), POST `/api/trading/approvals/{id}/renew` (220) |
| `R/trading_decisions.py` | GET `/api/trading/decisions?account_id=&symbol=&agent_id=&limit=1..20` (13), GET `/api/trading/decisions/{id}` (36) |
| `R/opportunities.py` | GET `/api/trading/opportunities?agent_id=&limit=1..50` (13), GET `/api/trading/opportunities/{id}` (32) |
| `R/owner_actions.py` | GET `/api/owner-actions?thread_id=` (49), GET/POST `/api/owner-actions/mandate?agent_id=` (61/73), POST `/{id}/challenge` (98), POST `/{id}/decision` (112), POST `/{id}/renew` (126) |
| `R/secret_cards.py` | POST `/api/owner-actions/{id}/secret` (69) |
| `R/chatgpt_sign_in.py` | POST `/api/owner-actions/{id}/chatgpt/start` (96), POST `/{id}/chatgpt/finish` (108), POST `/api/providers/openai_chatgpt/sign-out` (161) |
| `R/tasks.py` | GET `/api/tasks?agent_id=` (16), POST `/api/tasks?agent_id=&thread_id=` (32), GET `/api/tasks/{id}` (46), POST `/api/tasks/control` (54), POST `/api/tasks/{id}/complete` (62) |
| `R/collaboration.py` | GET `/api/threads/{id}/collaboration` (13), GET `/api/collaboration/{session_id}` (23) |
| `R/watches.py` | resource router `/api/watches` + POST `/api/watches/{id}/control` (28) |
| `R/events.py` | GET `/api/events?cursor=&thread_id=` (24), GET `/api/events/stream?cursor=&live=` (104) |
| `W/events.py` | WS `/api/ws/events` (64) |
| `W/market.py` | WS `/api/ws/market` (17) |
| `W/voice.py` | WS `/api/ws/voice` (19) |

### 3.3 The generic resource router

`resource_router(path, repository)` (VERIFIED `R/__init__.py:11-77`) gives every resource below the same
five routes:

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `{path}?agent_id=&thread_id=` | - | `Resource[]`, newest first, **max 200, no cursor/offset** (VERIFIED `D/transactions.py` `ResourceRepository.list`, `.limit(200)`) |
| POST | `{path}` (201) | `ResourceInput {agent_id?, thread_id?, payload: {...}}` | `Resource` |
| GET | `{path}/{id}` | - | `Resource` or `404 <kind>_not_found` |
| PUT | `{path}/{id}` | `ResourceUpdate {version >= 1, payload}` (full replace) | `Resource` (`version` + 1) or `409 version_conflict` |
| DELETE | `{path}/{id}` | - | `{"deleted": true}` |

`Resource` shape (VERIFIED `D/transactions.py:21-31`, `T/domain.ts:113-122`):

```json
{"id": "uuid", "agent_id": "uuid|null", "thread_id": "uuid|null",
 "payload": {}, "state": {}, "version": 1,
 "created_at": "ISO-8601", "updated_at": "ISO-8601"}
```

Each create/update/delete emits a durable event `<kind>.created|updated|deleted` with
`payload {"id", "version"?}` (VERIFIED `D/transactions.py:181,220,233`).

| Router path | Kind | Payload model | Evidence |
|---|---|---|---|
| `/api/artifacts` | `artifacts` | none (free dict) | `D/artifacts.py:8-12` |
| `/api/boards` | `boards` | `Board {title 1..160, columns: [str]=["todo","working","done"]}` | `D/boards.py`, `C/domain.py:202-204` |
| `/api/tickets` | `tickets` | `Ticket {board_id, title, description, status, run_id?}`; update refused `409 task_use_control` for task tickets | `D/tickets.py`, `C/domain.py:207-214` |
| `/api/scratchpad` | `scratchpad` | `ScratchpadItem {title 1..160, content <= 30000}` | `C/domain.py:217-219` |
| `/api/groups` | `groups` | `GroupCreate` | `D/groups.py`, `C/groups.py:6-20` |
| `/api/peer-messages` | `peer_messages` | none (read-only use) | `D/peer_messages.py` |
| `/api/skills` | `skills` | `AgentSkill {name 1..80, content 1..16000, enabled, manifest?}` + version history | `D/skills.py:12-16`, `C/skills.py:70-74` |
| `/api/agent-goals` | `agent_goals` | `AgentGoal {title, description, done}`; `agent_id` required, `thread_id` forbidden | `D/agent_goals.py` |
| `/api/knowledge-links` | `knowledge_links` | `KnowledgeLink {title, url http(s), note}`; agent-bound | `C/knowledge.py:10-25` |
| `/api/charts` | `cloud_charts` | chart state; catalog omits `state.scene` | `R/charts.py:12` |
| `/api/watches` | `market_watches` | `Watch` | `D/market_watches.py:18-21` |
| `/api/mcp` | `mcp` | `McpConnection {name, url https, url_secret_id?, endpoint_sha256?, secret_id?, enabled}` | `R/mcp.py:53-67`, `C/mcp.py:8-23` |
| `/api/integrations` | `integrations` | `Integration {type, name, url?, secret_id?, domain?, enabled, thread_id?, deliver_to_agent_id?, allowed_destinations[]}` | `R/integrations.py:71`, `C/integrations.py:17-29` |

Safety: generic `POST/PUT /api/artifacts` accept an arbitrary payload dict (no model). A native client
should only use `upload`, `text`, `file`, GET and DELETE for artifacts. INFERRED.

---

## 4. Realtime channel

There is one durable, owner-wide event feed (`ln_events`), exposed three ways. All three share the
envelope and cursor.

### 4.1 Envelope

VERIFIED `D/events.py:64-73`, `C/events.py:10-17`, `T/events.ts:2-10`:

```json
{
  "cursor": 123456,
  "kind": "run.delta",
  "thread_id": "uuid|null",
  "agent_id": "uuid|null",
  "run_id": "uuid|null",
  "payload": { },
  "created_at": "2026-11-27T10:00:00.000000+00:00"
}
```

Cursor semantics (VERIFIED `D/events.py:28-61,76-101`):

- `cursor` is a deployment-wide counter assigned **at publication after commit**
  (`publish_committed`), so a late-committing transaction can never appear behind a cursor the client
  already passed. Strictly increasing per owner feed; gaps between an owner's cursors are normal
  (other owners / internal rows). Not per thread.
- Reads return events with `cursor > requested`, ordered, at most 200 per page (500 hard cap).
- `current_event_cursor` = max published cursor for the owner (used by `live`).
- No event pruning/retention code exists (only a delivery-rule count query touches `created_at`).
  INFERRED: replay from cursor 0 replays the owner's entire history.

### 4.2 Native WebSocket `/api/ws/events` (what the Expo app uses)

Handshake (VERIFIED `W/events.py:64-121`):

1. Connect `wss://<server>/api/ws/events`. If an `Origin` header is present it must equal
   `LONORA_ALLOWED_ORIGIN`, else the socket is closed 1008 before accept (`W/events.py:67-69`).
   A native client should send **no** Origin header (dart:io `WebSocket.connect` sends none unless
   given; INFERRED) or exactly the allowed origin.
2. Within **10 s** send one JSON object:
   ```json
   {"token": "<bearer>", "cursor": 0, "live": true}
   ```
   - `token`: string, falls back to the `lonora_session` cookie (`W/events.py:77`).
   - `cursor`: integer 0..2^63-1 (`websocket_cursor_invalid`, close 1008 otherwise).
   - `live: true` **and** `cursor == 0`: the server replaces the cursor with the owner's current max
     (no history replay). A non-zero cursor is never jumped forward (`W/events.py:85-90`).
3. Server sends `{"type": "ready", "cursor": <effective cursor>}` (`W/events.py:93`).
4. Then each event envelope as a JSON text frame (no `type` key), and `{"type": "ping"}` every 15 s
   (`W/events.py:18,96-102`). The ping timer is not reset by events, so pings also interleave with
   traffic. Pings carry no cursor.
5. The server re-validates the token every 5 s; on revocation/expiry/any `LonoraError` it closes with
   **1008**; a producer that ends closes with 1000 (`W/events.py:36-61`).
6. Frames the client sends after the handshake are read and discarded (only disconnect is observed)
   (`W/events.py:31-34`). There is no subscribe/unsubscribe, no thread filter, no client ack.

Uvicorn also sends protocol-level WebSocket pings every 20 s with a 20 s timeout (library defaults,
not overridden in `A/server.py`). INFERRED from installed `uvicorn/config.py:209-210`.

Expo client behaviour to copy (VERIFIED `M/events.ts`):

- First connect sends `live: true` with `cursor: 0`; reconnects send the last consumed cursor without
  `live` (`:62-68`).
- Accept `ready` only if `ready.cursor >= cursor`; then call `onReconnect()` which **refreshes all
  canonical snapshots** (`:76-89`). This closes the admission gap described in
  `docs/chat-delivery-and-stream.md` step 8 and `R/events.py:57-58`.
- Drop events with `cursor <= last` (duplicates) and advance the cursor only after handling (`:93-102`).
- Arm a 10 s timer for `ready` and a 45 s idle timer thereafter (`IDLE_MS`), replace a silent socket;
  reconnect after 1.5 s; replace the socket on network-type change; close in background and reconnect
  on foreground (`:10,38,53,110-134`).
- Malformed JSON closes the socket and resumes from the last consumed cursor (`:103-105`).

### 4.3 SSE `/api/events/stream` (alternative; Bearer header supported)

VERIFIED `R/events.py:35-119`:

- `GET /api/events/stream?cursor=<n>&live=<bool>` with `Authorization: Bearer`.
- `Last-Event-ID` header is honored: effective cursor = `max(query cursor, Last-Event-ID)`;
  non-integer → `400 event_cursor_invalid`.
- `live=true` with cursor 0 and no `Last-Event-ID` starts at the current max.
- Frames: `id: <cursor>\nevent: ready\ndata: {"cursor": N}`; events `id: <cursor>\ndata: <envelope>`;
  `event: ping\ndata: {}` every 15 s (no `id:`, so `Last-Event-ID` never moves).
- Token re-checked every 5 s; stream ends on revocation.
- Response headers `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`; Caddy flushes this
  path immediately (`flush_interval -1`, VERIFIED `infra/compose/Caddyfile.prod`).

### 4.4 Poll `/api/events`

`GET /api/events?cursor=<n>&thread_id=<optional>` returns up to 200 envelopes after the cursor
(thread filter supported only here). VERIFIED `R/events.py:24-32`, `D/events.py:76-88`.

### 4.5 Server internals that affect latency

The server polls the DB every 0.1 s for 5 s after any event, else every 0.5 s. VERIFIED
`packages/bus/src/lonora_bus/durable_events.py:10-27`. Expect up to ~0.5 s delivery latency on an idle
feed. INFERRED.

### 4.6 Event kind catalog

Kinds found at emit sites (VERIFIED by grep of `emit(` across `packages/` and `apps/api`). Payload
columns marked VERIFIED were read; others are UNKNOWN and should be treated as "invalidate and
refetch".

| Kind | Payload | Client action | Evidence |
|---|---|---|---|
| `message.created` | full message (`message_data`; `reactions: []`, `superseded_by: null`) | merge by id; reconcile outbox by `client_nonce` | VERIFIED `D/messages.py:55-78,580` |
| `message.updated` | full message as a history page shows it | replace if present | VERIFIED `D/messages.py:583-587`; `D/voice_notes.py:77` |
| `message.reaction_updated` | `{thread_id, message_id, reactions: [{reactor, emoji, created_at}]}` | replace reaction list | VERIFIED `C/events.py:20-25` |
| `thread.updated` | `{thread_id, options: {web_search}}` | update thread options | VERIFIED `C/events.py:28-32` |
| `thread.read` | `{thread_id, last_read_seq}` | update unread | VERIFIED `D/thread_prefs.py:95-118` |
| `thread.prefs_updated` | `ThreadPrefs` | update row | VERIFIED `D/thread_prefs.py:206,248,287` |
| `chat_list.updated` | `{id, deleted?}` | refetch lists | VERIFIED `D/chat_lists.py:92,106,112,136` |
| `run.queued` | `{run: Run, reason_code?}` | upsert run | VERIFIED `D/runs.py:236-245,594-602` |
| `run.leased` / `run.recovered` | `{fence, run}` | upsert run | VERIFIED `D/runs.py:358-366` |
| `run.running`, `run.waiting_input`, `run.retry_scheduled`, `run.context_started`, `run.context_ready`, `run.context_compacted` | small / UNKNOWN | activity line; refetch run | VERIFIED kinds `packages/agent-runtime/src/lonora_agent/executor.py`, `progress.py:19` |
| `run.reply_started` | stream identity: `{turn_id, provider?, model?, input_seq, fence, generation, sequence: 0, phase: "streaming", message_id: null, truncated: false}` | start a new generation | VERIFIED `D/streaming.py:24-38,147-162`; `progress.py:41-42` |
| `run.delta` | `{turn_id, text: <appended chunk <= 1024 chars>, input_seq, fence, generation, sequence, phase, message_id, truncated, rich_content?: <cumulative>}` | append | VERIFIED `progress.py:11,43-86`, `D/streaming.py:41-68` |
| `run.rich_partial` | stream identity + cumulative `rich_content`, no text | replace rich preview | VERIFIED `progress.py:50-61,87-93` |
| `run.reply_committed` | stream identity with `phase: "committed" \| "discarded"`, `message_id`, `rich_content?` | settle; the real message arrives as `message.created` | VERIFIED `D/runs.py:477-486`, `D/streaming.py:114-144` |
| `run.completed` | none | mark done | VERIFIED `D/runs.py:515-522` |
| `run.failed` | `{code, failure: {family: quota\|rate\|timeout\|model\|other, retry_after_seconds, provider?}}` | show failure (skip when `run.background`) | VERIFIED `D/runs.py:556-562`, `C/runs.py:32-43` |
| `run.cancelled` | `{cancelled_by?}` | mark cancelled | VERIFIED `D/cancellation.py:44-52` |
| `tool.started` | `{name, call_id, toolset?, effect?: "read"\|"change"\|"financial"}` | activity line | VERIFIED `packages/agent-runtime/src/lonora_agent/tool_block.py:149-157` |
| `tool.completed` / `tool.failed` / `tool.cancelled` | `{name, call_id, ok?, code?}` | activity line | VERIFIED `tool_block.py:100-115` |
| `attention.updated`, `attention.ready` | `AttentionNotification` | refresh attention; `ready` also drives push | VERIFIED `C/attention.py:127-140`, `packages/gateway/src/lonora_gateway/push.py:158-176` |
| `owner_action.updated` | `{id, kind, status, status_reason, thread_id, transition_id}` | refetch `/api/owner-actions?thread_id=` | VERIFIED `D/owner_actions.py:608-624` |
| `trading.approval.updated` | full approval (`approval_data`) | replace card | VERIFIED `D/trade_approvals.py:33-63` |
| `agent.updated` | full agent (`agent_data`) | replace | VERIFIED `R/agents.py:115`, `D/agents.py:13-35` |
| `agent.created`, `agent.model.updated`, `agent.permission.updated`, `agent.trading_mode.updated`, `agent.personal_initialized`, `account_authority.updated` | UNKNOWN | refetch agent | kinds VERIFIED by grep |
| `voice.incoming.updated` | `call_data` (`{id, agent_id, thread_id, status, reason, attention_id, expires_at, version, execution_authorized: false}`) | ring UI | VERIFIED `packages/voice/src/lonora_voice/incoming.py:55-66,265-272` |
| `artifacts.updated` | `{id, version}` | refetch artifact | VERIFIED `R/artifacts.py:158-165` |
| `<kind>.created/updated/deleted` (resources) | `{id, version?}` | refetch | VERIFIED `D/transactions.py:181,220,233` |
| `cloud_charts.scene_updated`, `cloud_charts.refresh_requested` | `{id}` (refresh) | reread scene | VERIFIED `R/charts.py:31-37`; Expo `app/charts.tsx:190-195` |
| `broker_identity.updated`, `broker.degraded`, `broker.recovered`, `broker.external_activity`, `market_data.recovered`, `market.quote_updated`, `market.relationship_recorded`, `market_watches.updated`, `watch.expired`, `watch.suspended_health`, `watch.resumed_health` | UNKNOWN | refetch relevant view | kinds VERIFIED |
| `task.created/updated/failed/degraded/waiting/woken/resumed/retry_scheduled/attention_required` | UNKNOWN | refetch tasks | kinds VERIFIED |
| `collaboration.updated/completed/synthesis_scheduled`, `peer.requested`, `peer_messages.updated` | UNKNOWN | refetch | kinds VERIFIED |
| `memory.updated`, `owner_profile.updated`, `knowledge_notes.created/updated/deleted`, `skill.restored`, `skill.version_revoked`, `trusted_source.updated` | UNKNOWN | refetch | kinds VERIFIED |
| `trading.operation_updated/answered/resolved`, `trading.receipt_posted`, `opportunity.transition`, `supervision.intervention`, `notification.created` | UNKNOWN | refetch | kinds VERIFIED |
| `voice.transcript`, `voice.speech_interrupt_requested` | UNKNOWN | call UI | kinds VERIFIED |

The Expo thread screen applies `run.*` to its run list, accumulates streams, merges messages, and
schedules a debounced (150 ms) full refresh for every kind except the high-frequency
`run.delta`, `run.rich_partial`, `run.reply_started`, `run.progress`, `tool.*` (VERIFIED
`apps/mobile/app/thread.tsx:575-660`). It also runs a 15 s fallback refresh. The inbox/shell does
not use events: it polls `/agents`, `/groups`, `/threads/inbox`, `/chat-lists`, `/threads/settings`,
`/runs`, `/attention`, `/attention/view` every 5 s while foregrounded (VERIFIED
`M/shell-data.tsx:95-200`). A native client can be more event-driven, but must still refresh
snapshots after every `ready`.

---

## 5. Sending messages and the streamed reply

### 5.1 `POST /api/threads/{thread_id}/messages` (202)

Request `MessageCreate` (VERIFIED `C/domain.py:79-181`, `T/domain.ts:63-79`):

```json
{
  "content": "text, <= 30000 chars (required unless ui_submit or voice)",
  "client_nonce": "1..80 chars, default server uuid; client MUST supply and reuse on retry",
  "reply_to": "message id in the same thread | null",
  "attachment_ids": ["artifact id", "... max 10"],
  "mention_agent_ids": ["agent id"],
  "mention_all": false,
  "collaboration_session_id": null,
  "edited_from": "id of the owner's own earlier text message (edit and resend) | null",
  "input_answer": {"run_id": "", "question_id": "", "choice_id": ""},
  "ui_submit": {"source_message_id": "", "part": 0, "path": "0.1", "values": {}},
  "voice": {"artifact_id": "", "duration": 12.3, "peaks": [44 ints 0..100]},
  "command": {"name": "task|search|summary|skill", "argument": "", "skill_id": null}
}
```

Exclusivity rules (all VERIFIED `C/domain.py:150-181`; failures surface as `422 invalid_request`):
`voice` excludes every other field; `ui_submit` excludes `input_answer`, `attachment_ids`, `voice`,
`edited_from`; `command` requires `content` starting with `/` and ending with the argument, and
excludes voice/ui_submit/input_answer/edited_from/attachments. An `input_answer` must have
`content == choice.label` and no attachments/mentions (`422 input_answer_invalid`; VERIFIED
`D/messages.py` ~line 440-452).

Response (VERIFIED `D/messages.py:391-396,407-412,588-593`):

```json
{
  "message": { "...Message..." },
  "run_ids": ["uuid"],
  "runs": [ { "...Run, current projection..." } ],
  "deduplicated": false
}
```

Idempotency (VERIFIED `D/messages.py:335-396`):

- The nonce is scoped **per thread**. A repeat returns the stored message, its original `run_ids`, the
  current run projection and `deduplicated: true`. No new run starts.
- For a plain message, a repeat with **different** content is not rejected; the original wins.
  Only `ui_submit` mismatch (`409 ui_submit_conflict`) and `input_answer` mismatch
  (`409 input_answer_conflict`) are checked.
- Voice notes return `run_ids: []`; runs start after transcription (VERIFIED `D/messages.py:562-571`, `:566`).

Errors: `404 thread_not_found`, `404 reply_not_found`, `404 artifact_not_found`, `404 agent_not_found`
(mentions), `409 input_answer_expired`, `409 agent_paused`, `409 collaboration_thread_mismatch`,
`409 collaboration_session_required`, `422 voice_artifact_invalid`, `422 message_command_invalid`,
`422 invalid_request`. VERIFIED `D/messages.py:420-525`.

Side effects: first message sets an empty thread title to `content[:80]` (`D/messages.py:560`);
`message.created` is emitted; an edit also emits `message.updated` for the original.

Client delivery rules (VERIFIED `docs/chat-delivery-and-stream.md`, `M/outgoing-messages.ts`):
optimistic bubble keyed by nonce (`id: "pending:<nonce>"`), retry with the same nonce, auto-flush only
plain text when the API never answered; input answers, edits, card submits and voice notes are never
queued offline. The ACK already contains the run projection.

### 5.2 Message shape

VERIFIED `D/messages.py:55-78`, `T/domain.ts:80-112`, plus read-time fields added by the history route
(`consumed`, `ui_lock`, `ui_mark`; VERIFIED `R/messages.py:42-50`):

```json
{
  "id": "uuid", "thread_id": "uuid", "agent_id": "uuid|null", "seq": 42,
  "role": "user|assistant|system|tool", "content": "plain/markdown text",
  "rich_content": {"version": 1, "parts": [ ... ]} ,
  "reply_to": "uuid|null", "mentions": {"agent_ids": [], "all": false, "session_id": null},
  "attachment_ids": [], "created_at": "ISO", "client_nonce": "str|null",
  "origin": "owner|ui_submit|ui_follow_up", "ui_submit": {}, "ui_state": {},
  "suggested_reply": "<= 60 chars|null", "edited_from": "uuid|null", "superseded_by": "uuid|null",
  "reactions": [{"reactor": "owner|<agent id>", "emoji": "👍", "created_at": "ISO"}],
  "consumed": true
}
```

`rich_content.parts[]` types (VERIFIED `T/visual-response.ts:100-141`, `T/genui.ts:55`):
`text {text}`, `ui {document: UiDocument v2, building?, cut?}` (or legacy v1 `VisualDocument`),
`voice {artifact_id, duration, peaks[44], transcript_status: pending|done|failed}`,
`call {direction, duration_seconds, missed}`, `command {name, argument, skill_id?, skill_name?}`.

### 5.3 History pagination

`GET /api/threads/{id}/messages?limit=1..200 (default 100)&before=<seq>` or `&around=<seq>`
(VERIFIED `R/messages.py:21-50`, `D/messages.py:137-195`):

- Ascending by `seq`. `before`: newest `limit` messages with `seq < before`. Page backwards with
  `before = <oldest loaded seq>`.
- `around`: the target, up to `limit//2` before, the rest after; `404 message_not_found` if hidden.
- Messages at or before the owner's "clear" floor are never returned.
- Owner messages carry `consumed` (the agent's run has started on it).

### 5.4 Reactions, replies, edits, read state

| Operation | Route | Notes | Evidence |
|---|---|---|---|
| Set reaction | PUT `/api/threads/{t}/messages/{m}/reactions/{emoji}` | one per reactor; one of `👍 ❤️ 😂 😮 😢 🙏` (URL-encode); returns `{message_id, reactions}` | VERIFIED `R/messages.py:68-78`, `C/reactions.py:14` |
| Remove reaction | DELETE `/api/threads/{t}/messages/{m}/reactions` | | VERIFIED `R/messages.py:81-89` |
| Reply / quote | `reply_to` in `MessageCreate` | same thread only | VERIFIED `D/messages.py:502-506` |
| Edit and resend | `edited_from` | original gets `superseded_by` | VERIFIED `C/domain.py:142`, `D/messages.py:528,583-587` |
| Mark read | POST `/api/threads/{id}/read` `{"seq": n}` | max-wins, clamped to latest, clears `marked_unread`; returns `ThreadPrefs` | VERIFIED `R/threads.py:142-150`, `D/thread_prefs.py:95-118` |
| Read all | POST `/api/threads/read-all` | returns `ThreadPrefs[]` | VERIFIED `R/threads.py:49-54` |
| Clear history | POST `/api/threads/{id}/clear` | hides for the owner only | VERIFIED `R/threads.py:164-170` |
| Unlock a sent card | POST `/api/threads/{t}/messages/{m}/ui-state/{part}/unlock` | cancels an unstarted submit | VERIFIED `R/messages.py:53-65` |

Message deletion: no route. Forwarding: no route. VERIFIED (route list).

### 5.5 Runs: cancel, resume, retry, takeover

`Run` shape (VERIFIED `D/runs.py:86-134`, `T/runs.ts:45-75`):

```json
{
  "id": "uuid", "thread_id": "uuid", "agent_id": "uuid", "parent_run_id": "uuid|null",
  "status": "queued|leased|running|waiting_input|waiting_takeover|completed|failed|cancelled",
  "trigger": "user|group|routine|watch|...", "background": false, "input_seq": 41,
  "error_code": "str|null", "failure": {"family": "rate", "retry_after_seconds": 30, "provider": "openai"},
  "result": "str|null", "model_metadata": {"activity": {"kind": "tool.started", "name": "..."}},
  "stream": {"turn_id": "", "input_seq": 41, "fence": 3, "generation": 2, "sequence": 17,
             "text": "", "truncated": false, "phase": "streaming", "message_id": null, "rich_content": null},
  "input_requests": [{"id": "", "run_id": "", "message_id": "", "thread_id": "", "question": "",
                      "choices": [{"id": "", "label": "", "effects": []}], "status": "pending",
                      "selected_choice_id": null, "answer_message_id": null}],
  "input_request": { },
  "created_at": "ISO", "updated_at": "ISO"
}
```

| Action | Route | Semantics | Errors | Evidence |
|---|---|---|---|---|
| List | GET `/api/runs?thread_id=` | latest 100; with thread: its runs, their children, and background runs whose questions were copied here | | VERIFIED `R/runs.py:21-43` |
| Read | GET `/api/runs/{id}` | | `404 run_not_found` | VERIFIED `R/runs.py:54-63` |
| Cancel ("Stop") | POST `/api/runs/{id}/cancel` `{}` | cancels non-terminal run and its non-terminal children; returns Run | `404 run_not_found` | VERIFIED `R/cancellation.py:16-31`, `D/cancellation.py:29-66` |
| Resume / takeover | POST `/api/runs/{id}/resume` `{}` | only from `waiting_input`, `waiting_takeover` or `failed` → `queued` | `409 run_cannot_resume`, `409 task_resume_required` | VERIFIED `R/runs.py:83-99`, `packages/session/src/lonora_session/continuation.py:4-7` |
| Retry | POST `/api/runs/{id}/retry` `{}` (202) | new Run for the same input; idempotent per failed run; never for financial runs | `409 run_not_retryable`, `409 run_retry_too_early` with `{"code","retry_after_seconds"}`, `409 agent_paused` | VERIFIED `R/runs.py:66-80`, `D/run_retry.py:36-41,105-131` |
| Create (low-level) | POST `/api/runs` `RunRequest {thread_id, agent_id, trigger, prompt, parent_run_id, metadata}` | arbitrary trigger; protected metadata keys stripped | | VERIFIED `R/runs.py:46-51`, `D/runs.py:186-215`. Not used by the Expo app; **do not use** |

There is no dedicated "takeover" endpoint; `waiting_takeover` is resumed with `/resume`. VERIFIED.

### 5.6 Streaming reply protocol

From `docs/chat-delivery-and-stream.md` and code (VERIFIED where cited):

- A run streams through `run.reply_started` → `run.delta`* / `run.rich_partial`* → `run.reply_committed`,
  then the canonical `message.created` (VERIFIED `D/runs.py:477-498`).
- Identity = `(run_id, turn_id, fence, generation)`; `sequence` counts chunks within a generation from 1.
  `fence` is the lease fence (a re-lease after a crash increments it); `generation` increments on every
  `run.reply_started` of the run (model fallback, privacy rewrite). VERIFIED `D/streaming.py:24-38`.
- `run.delta.text` is the **appended chunk**, never cumulative; providers' tokens are re-chunked to
  <= 1024 chars per event (`DELTA_CHUNK_CHARS`). `rich_content` is **cumulative** and only present on
  the last chunk of an emission that changed it. VERIFIED `progress.py:11,43-86`.
- Stream text is capped at 60000 code points; `truncated: true` once exceeded. VERIFIED
  `D/streaming.py:11,58-63`; client mirror `packages/core/src/reply-stream.ts:3`.
- A new generation must replace the preview (the old one was discarded). Compare `(fence, generation)`
  lexicographically and ignore older ones; ignore `sequence <= current`; a `sequence` jump marks a
  **gap**, after which the client refetches `GET /api/runs?thread_id=` and rebases on `run.stream`
  (the durable snapshot). VERIFIED reducer `packages/core/src/reply-stream.ts:20-150`; Expo
  `app/thread.tsx:588-594` (`if (value.gap) schedule()`).
- A terminal preview is never resurrected by delayed chunks; only a newer fence/generation replaces it.
- Cancel/failure keep the accepted preview as `phase: cancelled|failed`; a cut v2 card keeps built
  blocks with `cut`; no fake assistant message is created. VERIFIED `D/streaming.py:87-144`.
- Background runs (`run.background == true`) publish no `run.delta`/`run.rich_partial`; show only their
  final message; hide their failures unless the owner must act. VERIFIED doc step 10, `D/runs.py:121-125`.
- `run.reply_committed` with `phase: "discarded"` means no message will come for that generation.

---

## 6. Attachments and files

| Method | Path | Request | Response | Errors | Evidence |
|---|---|---|---|---|---|
| POST | `/api/artifacts/upload` (201) | `multipart/form-data`: `file` (required), `thread_id` (form, optional), `agent_id` (form, optional) | `Resource` with `payload {name <= 160 (sanitized), key, size, media_type, sha256, text_key?, text_chars?, page_image_keys?}` | `413 attachment_too_large`, `413 request_body_too_large`, `400 invalid_filename`, `404 thread_not_found`/`agent_not_found` | VERIFIED `R/artifacts.py:24-84`, `packages/core/src/lonora_core/attachments.py` |
| GET | `/api/artifacts/{id}/file?preview=true` | Bearer header | file bytes; `Content-Disposition` inline only with `preview=true` for png/jpeg/webp/gif/pdf/html/svg, else attachment; `Content-Security-Policy: sandbox; default-src 'none'`; ETag/Last-Modified; HTTP Range supported | `404 artifacts_not_found`, `404 artifact_file_missing` | VERIFIED `R/artifacts.py:172-205`; Starlette 1.10 FileResponse range/etag (installed `starlette/responses.py:324-344`) |
| PUT | `/api/artifacts/{id}/text` | `{expected_version, name 1..160, content <= 600000}` | `Resource` (new version), emits `artifacts.updated` | `409 version_conflict`, `409 artifact_not_text`, `413` | VERIFIED `R/artifacts.py:110-169` |
| GET | `/api/artifacts?thread_id=&agent_id=` | | `Resource[]` (<= 200, newest first, internal tool results excluded) | | VERIFIED `D/artifacts.py:14-33` |
| GET/DELETE | `/api/artifacts/{id}` | | `Resource` / `{"deleted": true}` | | VERIFIED `R/__init__.py` |

Flow: upload each file (show progress; the Expo app uses XHR for progress, VERIFIED `M/api.ts:187-238`),
collect `id`s, then send the message with `attachment_ids` (max 10). The upload is a separate
artifact even if the message is never sent. Images in messages are fetched via the authenticated
`/file` route (no public URLs). Content type: the multipart part's type is stored; an
octet-stream/empty type with a text suffix becomes `text/plain` (`R/artifacts.py:24-28`). PDFs get a
text layer and page images extracted for agents (`R/artifacts.py:31-44,72-73`).

Voice notes: upload audio (`audio/webm|ogg|mp4|mpeg|wav`, codec suffix ignored) with the same
`thread_id`, then send `{"voice": {...}, "client_nonce": ...}` with no content; transcription lands as
`message.updated`. VERIFIED `D/messages.py:38-52,515-571`. The Expo app does not record voice notes
(only the web app does; VERIFIED by grep of `peaks`).

---

## 7. Threads, inbox, chat lists, groups, collaboration

| Method | Path | Request | Response | Evidence |
|---|---|---|---|---|
| GET | `/api/threads?agent_id=` | | `Thread[]` | VERIFIED `R/threads.py:81-86` |
| POST | `/api/threads` (201) | `ThreadCreate {agent_id?, group_id?, title <= 160}` | `Thread` | VERIFIED `C/domain.py:73-76` |
| GET | `/api/threads/{id}` | | `Thread` | |
| DELETE | `/api/threads/{id}` | | `{"deleted": true}`; refused while a trade from it is uncertain; revokes grants signed there | VERIFIED `R/threads.py:105-127` |
| PUT | `/api/threads/{id}/options` | `{"web_search": bool}` | `Thread`; emits `thread.updated` | VERIFIED `R/threads.py:130-139` |
| GET | `/api/threads/inbox` | | `InboxEntry[]` | VERIFIED `R/threads.py:41-46`; shape `T/domain.ts:206-234` |
| PATCH | `/api/threads/{id}/prefs` | `ThreadPrefsUpdate {pinned?, muted?, archived?, favourite?, marked_unread?}` (at least one) | `ThreadPrefs`; 4th pin → `thread_pin_limit` | VERIFIED `C/thread_prefs.py:13-27` |
| POST | `/api/threads/prefs` | bulk: same + `thread_ids` (1..200) | `ThreadPrefs[]` | VERIFIED `C/thread_prefs.py:29-30` |
| GET/PUT | `/api/threads/settings` | `{"keep_archived": bool}` | same | VERIFIED `C/thread_prefs.py:37-41` |
| POST | `/api/agents/{id}/conversation` | `{}` | `Thread` (get-or-create the agent's direct chat) | VERIFIED `R/agents.py:87-92` |
| GET/POST | `/api/chat-lists` | `{"name": 1..30}` | `ChatList[]` / `ChatList` | VERIFIED `R/chat_lists.py`, `C/chat_lists.py:8-17` |
| PUT/DELETE | `/api/chat-lists/{id}` | `{name?, position?}` | `ChatList` / `{"deleted": true}` | VERIFIED `C/chat_lists.py:20-32` |
| PUT | `/api/chat-lists/{id}/members` | `{"thread_ids": [<= 500]}` (deduped) | `ChatList` | VERIFIED `C/chat_lists.py:35-41` |
| POST | `/api/groups/create` (201) | `GroupCreate {name 1..80, member_ids >= 1, participation="mentions_or_lead", purpose <= 160, lead_agent_id (must be member)}` | group `Resource` + `thread_id` | VERIFIED `R/groups.py:17-29`, `C/groups.py:6-20` |
| GET/PUT/DELETE | `/api/groups[/{id}]` | generic | | VERIFIED `R/groups.py:14` |
| GET | `/api/threads/{id}/collaboration` | | collaboration `Resource \| null` | VERIFIED `R/collaboration.py:13-20` |
| GET | `/api/collaboration/{session_id}` | | `Resource` | VERIFIED `R/collaboration.py:23-28` |
| GET | `/api/peer-messages?thread_id=&agent_id=` | | `Resource[]` (agent-to-agent exchanges shown in both threads) | VERIFIED `D/peer_messages.py` |

Shapes (VERIFIED `D/threads.py:19-27`, `D/thread_prefs.py:39-63`, `T/domain.ts:184-242`):

```json
// Thread
{"id": "", "agent_id": "|null", "group_id": "|null", "title": "", "options": {"web_search": false}, "created_at": ""}
// ThreadPrefs
{"thread_id": "", "last_read_seq": 0, "marked_unread": false, "muted": false, "archived": false,
 "favourite": false, "pinned_order": null, "hidden_before_seq": 0, "updated_at": null}
// InboxEntry
{"thread_id": "", "agent_id": null, "group_id": null,
 "last_message": {"id": "", "role": "assistant", "agent_id": "", "content": "", "created_at": "", "seq": 9,
                  "kind": "text|card|image|voice|file", "preview": "<= 160 chars",
                  "attachments": {"count": 0, "kinds": []}, "consumed": null},
 "last_activity_at": "", "unread_count": 2, "last_read_seq": 7, "marked_unread": false, "muted": false,
 "archived": false, "favourite": false, "pinned_order": null, "hidden_before_seq": 0}
// ChatList
{"id": "", "name": "", "position": 0, "thread_ids": [], "created_at": "", "updated_at": ""}
```

Pagination: inbox, threads and chat lists are unpaginated full lists. VERIFIED.

---

## 8. Agents

### 8.1 CRUD

| Method | Path | Request | Response | Errors | Evidence |
|---|---|---|---|---|---|
| GET | `/api/agents` | | `Agent[]` | | VERIFIED `R/agents.py:47-54` |
| POST | `/api/agents` (201) | `AgentCreate` | `Agent` | `422 agent_trading_binding_required` (no binding and not `flexible`), `409 broker_disabled`, `404 symbol_not_found`, `409 broker_symbol_mismatch`, `409 broker_connection_changed` | VERIFIED `R/agents.py:25-74` |
| GET | `/api/agents/{id}` | | `Agent` | `404 agent_not_found` | |
| PATCH | `/api/agents/{id}` | `AgentUpdate` (partial) | `Agent`; emits `agent.updated` | `403 agent_scope_change_forbidden`, `409 version_conflict` (scope revision) | VERIFIED `R/agents.py:95-116`, `D/agents.py` update (~line 105-107) |
| DELETE | `/api/agents/{id}` | | `{"deleted": true}`; refused while its trade is uncertain | | VERIFIED `R/agents.py:119-128` |

`AgentCreate` (VERIFIED `C/domain.py:20-38`):

```json
{"template": "trading|general|research|supervisor|null", "scope_mode": "fixed_market|flexible",
 "trading_account_id": "<= 36 | null", "trading_symbol": "<= 80 | null",
 "name": "1..80", "title": "<= 160", "description": "<= 2000", "instructions": "<= 16000",
 "avatar": "orb", "color": "#7c83fd"}
```

`AgentUpdate` (VERIFIED `C/domain.py:41-70`): every field optional: `title, description, name,
instructions, avatar, color, paused`; a scope change needs all of `scope_mode="flexible"`,
`trading_account_id`, `trading_symbol`, `expected_scope_revision`.

`Agent` response (VERIFIED `D/agents.py:13-35`, `T/domain.ts:8-33`):

```json
{"id": "", "name": "", "title": "", "description": "", "avatar": "face-smile", "color": "#8B5CF6",
 "instructions": "", "paused": false, "trading_mode": "full|ask", "trades_on_its_own": false,
 "role": "personal|general|specialist|delegated|legacy", "template": "trading|...|null",
 "scope_mode": "fixed_market|flexible", "scope_revision": 0, "scope": { },
 "trading_account_id": null, "trading_symbol": null, "parent_id": null, "created_at": ""}
```

### 8.2 Avatar fields

- `avatar` is a free string on the server (no validation); `color` must match `^#[0-9a-fA-F]{6}$`.
  VERIFIED `C/domain.py:37-38,68-69`. There is no avatar image upload.
- Clients interpret `avatar` as a face id from a fixed set of 16: `orb` ("Signals"), `face-smile`,
  `face-thoughtful`, `face-happy`, `face-wink`, `face-sleepy`, `face-surprised`, `face-angry`,
  `face-playful`, `face-excited`, `face-skeptical`, `face-dreamy`, `face-focused`, `face-worried`,
  `face-laugh`, `face-determined`; any other value renders as `orb`. VERIFIED
  `packages/core/src/trading-avatar-motion.js:62-86`, `apps/mobile/components/avatar-picker.tsx:11-28`.
- Palette: `AVATAR_COLORS` (hex list) with default violet `#8B5CF6`; server default `#7c83fd`.
  VERIFIED `packages/core/src/avatar-geometry.ts:333-337`, `C/domain.py:38`.
- Geometry/motion for drawing the animated avatar lives in `packages/core/src/avatar-geometry.ts`,
  `trading-avatar-motion.js` (docs `docs/avatar-facial-geometry.md`, `docs/avatar-motion.md`). A Flutter
  client must port these to look identical. INFERRED.
- A separate `Avatar {shape: orb|circle|square|diamond, color}` contract exists (`C/agent_avatar.py:8-10`)
  but is not used by agent routes. VERIFIED (grep).

### 8.3 Agent sub-resources

| Method | Path | Request | Response | Evidence |
|---|---|---|---|---|
| GET | `/api/agents/{id}/state` | | `AgentLiveState` (state, phase, waits, approvals, watches, tasks with can_pause/resume/cancel, health, `trading_readiness`) | VERIFIED `R/agent_state.py`, `T/agent-state.ts` |
| GET | `/api/agents/{id}/permissions` | | permission ladder state (read-only) | VERIFIED `R/agent_permissions.py` |
| GET | `/api/agents/{id}/performance?account_id=&symbol=` | | performance snapshot | VERIFIED `R/performance.py` |
| GET/PUT | `/api/agents/{id}/model` | `AgentModelChange {preference..., expected_revision?}` | `AgentModelRecord` | VERIFIED `R/agent_models.py:26-42`, `C/model_routing.py:90-100` |
| GET | `/api/agents/{id}/model/summary` | | `{record, current, available, connected_providers, usage{days, requests, input_tokens, output_tokens, cached_tokens, models}}` | VERIFIED `R/agent_models.py:45-84` |
| GET | `/api/agents/notifications` | | `{agent_id: AgentDeliveryRules}` | VERIFIED `R/agent_delivery.py:14-20` |
| GET/PUT | `/api/agents/{id}/notifications` | `{in_app?, calls?, daily_limit? 1..100}` | `AgentDeliveryRules {in_app, calls, daily_limit}` | VERIFIED `C/agent_delivery.py:16-25` |
| GET | `/api/agents/{id}/account-authorities` | | latest 20 authorities | section 11.5 |

---

## 9. Memory, knowledge, scratchpad, skills

| Method | Path | Request | Response | Evidence |
|---|---|---|---|---|
| GET | `/api/agents/{id}/memory` | | `{agent_id, content, version, updated_at}` | VERIFIED `D/memory.py:78-84` |
| PUT | `/api/agents/{id}/memory` | `{content <= 30000, version}` | commit result; `422 memory_user_section_moved` | VERIFIED `R/memory.py` (write) |
| GET | `/api/agents/{id}/memory/revisions?limit=1..50` | | revision list | VERIFIED |
| GET/PUT | `/api/owner/profile` | `{content, version}` | `{...profile, reach_me: IncomingCallPolicy, devices: [{id,name}], delivery: "in_app_only", shared_with: "every_agent"}` | VERIFIED `R/memory.py` `profile_payload` |
| GET/POST | `/api/owner/profile/lines` | `{version, text, replacement?}` | profile lines ("what I know about you") | VERIFIED |
| PUT | `/api/owner/preferences` | `{reply_language?, reach_me?: IncomingCallPolicy, name? <= 80, address? <= 80}` | profile payload | VERIFIED |
| GET | `/api/owner/profile/revisions?limit=` | | revisions | VERIFIED |
| POST | `/api/memory/revisions/{id}/revert` | `{version?}` | `{document, result}` | VERIFIED |
| GET/PUT | `/api/memory/semantic/config` | `SemanticConfig` | same; `422 semantic_model_required` | VERIFIED |
| POST | `/api/agents/{id}/memory/semantic` (201) | `SemanticNote` | indexed note | VERIFIED |
| GET | `/api/agents/{id}/knowledge` | | `KnowledgeItem[] {id, type: note\|link, title, content, url, version, updated_at}` | VERIFIED `R/knowledge.py:19-24`, `C/knowledge.py` |
| POST | `/api/agents/{id}/knowledge/notes` (201) | `KnowledgeNote {title 1..160, content 1..8000}` | note | VERIFIED `R/knowledge.py:27-42` |
| PUT/DELETE | `/api/agents/{id}/knowledge/notes/{note_id}` | same | replaces (new id) / `{"deleted": true}`; `404 knowledge_note_not_found` | VERIFIED `R/knowledge.py:45-82` |
| CRUD | `/api/knowledge-links`, `/api/agent-goals` | generic resource, `agent_id` required | | VERIFIED `R/agent_goals.py` |
| CRUD | `/api/scratchpad` | generic resource `ScratchpadItem` | | VERIFIED `R/scratchpad.py` |
| CRUD | `/api/skills?agent_id=` | generic resource `AgentSkill` (validated graph; package skills refuse edit `409 skill_package_lifecycle_required`) | | VERIFIED `R/agent_skills.py:34-121` |
| GET | `/api/skills/{id}/versions` | | version list | VERIFIED `R/agent_skills.py:124` |
| POST | `/api/skills/{id}/restore` | `{version, expected_version}` | `Resource` | VERIFIED `R/agent_skills.py:134-153` |
| GET | `/api/agents/{id}/skills/catalog?offset=0&limit=1..100` | | `SkillCatalog` (offset pagination) | VERIFIED `R/agent_skills.py:186-203` |
| GET | `/api/agents/{id}/skills/catalog/{skill_id}` | | entry | VERIFIED |
| GET/POST | `/api/agents/{id}/skills/revocations` | `SkillRevokeRequest {skill_id, version, expected_revision, reason}` | controls | VERIFIED `C/skills.py:43-45` |

---

## 10. Routines, tasks, tickets, boards, watches, opportunities, decisions

| Method | Path | Request | Response | Evidence |
|---|---|---|---|---|
| GET | `/api/routines?agent_id=` | | `Routine[]` by `next_run_at` | VERIFIED `R/routines.py:19-30` |
| POST | `/api/routines/{agent_id}` (201) | `RoutineCreate {title? <= 160, prompt 1..8000, exactly one of interval_seconds 60..31536000 \| cron \| run_at (tz-aware), timezone="UTC", enabled}` | `Routine` | VERIFIED `C/routines.py:8-40` |
| PUT | `/api/routines/{id}` | `RoutineUpdate` (partial) | `Routine`; errors `422 one_schedule_required`, `run_at_past`, `run_at_timezone_required` as `code` | VERIFIED `R/routines.py:43-56` |
| DELETE | `/api/routines/{id}` | | `{"deleted": true}` | |
| GET | `/api/routines/{id}/history` | | execution history | VERIFIED |
| GET | `/api/tasks?agent_id=` | | task snapshots (20 per agent, else 100) | VERIFIED `R/tasks.py:16-29` |
| POST | `/api/tasks?agent_id=&thread_id=` (202) | `TaskCreate {title, description, completion_mode finite\|continuous, steps[], retry_policy, due_at?, completion_criteria}` | snapshot | VERIFIED `C/tasks.py:40-62` |
| GET | `/api/tasks/{id}` | | snapshot | |
| POST | `/api/tasks/control` | `TaskControl {task_id, action: pause\|resume\|cancel\|revise, expected_version, instruction?, steps?}` | snapshot | VERIFIED `C/tasks.py:88-94` |
| POST | `/api/tasks/{id}/complete` | `{expected_version}` | snapshot | VERIFIED `R/tasks.py:62-73` |
| CRUD | `/api/tickets`, `/api/boards` | generic | | section 3.3 |
| POST | `/api/tickets/{id}/start` (202) | | start result | VERIFIED `R/tickets.py` |
| CRUD | `/api/watches` | generic (`Watch` model) | | |
| POST | `/api/watches/{id}/control` | `{action: cancel\|pause\|resume\|extend, hours 1..24 (extend only)}` | `Resource` | VERIFIED `R/watches.py:9-41` |
| GET | `/api/trading/opportunities?agent_id=&limit=` | | opportunities | VERIFIED `R/opportunities.py:13-29` |
| GET | `/api/trading/opportunities/{id}` | | opportunity + history (refreshes state) | VERIFIED `R/opportunities.py:32-40` |
| GET | `/api/trading/decisions?...&limit=1..20` | | decision summaries (read-only replay) | VERIFIED `R/trading_decisions.py` |
| GET | `/api/trading/decisions/{id}` | | `TradingDecision` | |

`Routine` shape: `T/domain.ts:123-139`.

---

## 11. Owner actions, approvals, trading controls, authority

### 11.1 Owner action cards (permission / approval cards)

Kinds: `settle_operation`, `trading_mode` (Mandate card), `secret`, plus `supervision_paused` in TS.
VERIFIED `C/owner_actions.py:20-28`, `T/owner-actions.ts:4-10`.

| Method | Path | Request | Response | Errors | Evidence |
|---|---|---|---|---|---|
| GET | `/api/owner-actions?thread_id=` (required) | | `OwnerAction[]` of the thread | `404 thread_not_found` | VERIFIED `R/owner_actions.py:49-58` |
| GET | `/api/owner-actions/mandate?agent_id=` | | the agent's live Mandate card or `null` | | VERIFIED `R/owner_actions.py:61-70` |
| POST | `/api/owner-actions/mandate?agent_id=` | `{}` | raises/returns the Mandate card | | VERIFIED `R/owner_actions.py:73-95` |
| POST | `/api/owner-actions/{id}/decision` | `OwnerActionDecision {decision: confirm\|cancel, trading_mode?: full\|ask, outcome?: executed\|not_executed\|unknown}` | updated `OwnerAction` | `422 owner_action_trading_mode_required`, `owner_action_outcome_required`, `owner_action_secret_values_required`, `owner_action_decision_unsupported`, `owner_action_kind_unsupported`; `409 owner_action_already_decided` | VERIFIED `R/owner_actions.py:112-245`, `C/owner_actions.py:241-250` |
| POST | `/api/owner-actions/{id}/renew` | `{}` | fresh card; `owner_action_not_renewable` | | VERIFIED `R/owner_actions.py:126-133` |
| POST | `/api/owner-actions/{id}/challenge` | | always `409 owner_action_passkey_not_needed` (or `owner_action_expired_or_decided`) | | VERIFIED `R/owner_actions.py:98-109` |
| POST | `/api/owner-actions/{id}/secret` | `SecretCardSave {values: {"ENV_NAME": "value 1..16000"}}` (<= 8) | updated `OwnerAction` (values never echoed) | `409 chatgpt_sign_in_required` for ChatGPT cards; stale → card settles `expired` | VERIFIED `R/secret_cards.py:69-120`, `C/owner_actions.py:57-67` |
| POST | `/api/owner-actions/{id}/chatgpt/start` | `{new_account?: bool}` (body optional) | `{authorization_url, account, ...}`; open URL in browser | | VERIFIED `R/chatgpt_sign_in.py:96-105`; Expo `components/owner-action-card.tsx:157-168` |
| POST | `/api/owner-actions/{id}/chatgpt/finish` | `{address: "<the redirect URL the browser landed on>"}` | updated `OwnerAction` | | VERIFIED `R/chatgpt_sign_in.py:108-158` |

How to approve/deny:

- Mandate: `{"decision":"confirm","trading_mode":"<the mode the button showed>"}`; result
  `{trading_mode, withdrawn}` (withdrawn pending trade approvals). VERIFIED `R/owner_actions.py:136-164`;
  Expo `components/agent-permissions.tsx:82-84`, `M/mandate-mode.ts`.
- Settle uncertain operation: `{"decision":"confirm","outcome":"executed|not_executed|unknown"}`.
- Secret: values only through `/secret`; `cancel` via `/decision`.
- Any card: `{"decision":"cancel"}` to dismiss. Repeating a decision is idempotent.

`OwnerAction` shape (VERIFIED `D/owner_actions.py:577-605`, `T/owner-actions.ts`):

```json
{"id": "", "kind": "trading_mode", "status": "pending|confirmed|cancelled|expired|superseded",
 "status_reason": null, "superseded_by": null, "source": "agent|system|owner",
 "agent_id": "", "thread_id": "", "run_id": "", "timeline_seq": 17,
 "facts": {"several_accounts": false, "trading_mode": "ask", "agent": {"exists": true, "name": ""},
           "operation": {}, "secret": {"label": "", "fields": [{"key": "", "label": "", "secret": true, "role": null, "required": true}],
                           "destination": "workspace|broker", "agent_name": ""}},
 "requires_passkey": false, "result": {}, "expires_at": "", "decided_at": null,
 "decided_via": null, "created_at": "", "updated_at": ""}
```

### 11.2 Trade approvals and receipts

| Method | Path | Request | Response | Errors | Evidence |
|---|---|---|---|---|---|
| GET | `/api/trading/approvals?thread_id=` | | approvals (<= 200), expired ones settled lazily; journal-reconciled results | | VERIFIED `R/trading.py:137-193` |
| POST | `/api/trading/approvals/{id}/decision` | `{"decision": "approve"\|"reject"}` | approval | `409 trade_approval_expired`; price-band drift check on approve | VERIFIED `R/trading.py:133-217` |
| POST | `/api/trading/approvals/{id}/renew` | `{}` | `Run` (agent asked again) | | VERIFIED `R/trading.py:220-231` |
| GET | `/api/trading/receipts?thread_id=` | | execution receipts | | VERIFIED `R/trading.py:123-130` |
| GET | `/api/trading/journal?account_id=&thread_id=` | | journal entries | | VERIFIED `R/trading.py:109-120` |

Approval shape (VERIFIED `D/trade_approvals.py:33-52`):
`{id, run_id, thread_id, agent_id, timeline_seq, requests[], contracts[], status, results[], reason,
tolerance, reference_price, expires_at, created_at}`.

A push for an approval never carries an action; approval happens only inside the app with the owner
session. VERIFIED `packages/gateway/src/lonora_gateway/push.py:17-21`.

### 11.3 Trading controls

- **There is no global trading ON/OFF and no emergency-stop endpoint.** "Lonora has no Stop control
  (owner amendment 1 to VISION.md); the owner's brake is the pause of an agent or of one piece of its
  work." VERIFIED `docs/trading-safety.md:7-8`; no route found by grep for emergency/kill.
- Per agent, the only trading switch is `trading_mode` `full|ask`, changed only via the Mandate card
  decision (owner tap). VERIFIED `C/trading.py:11`, `R/owner_actions.py:136-164`.
- Brakes available to a client:
  - Pause/resume an agent: `PATCH /api/agents/{id} {"paused": true|false}`. VERIFIED `C/domain.py:70`.
  - Pause/cancel a task: `POST /api/tasks/control`.
  - Pause/cancel a watch: `POST /api/watches/{id}/control`.
  - Cancel a run: `POST /api/runs/{id}/cancel`.
  - Stop workspace processes: `POST /api/workspace/running/stop` `{pid, agent_id}` or `/stop-all`.
    VERIFIED `R/workspace_running.py:17-48`.
  - Revoke a signed account authority: `POST /api/account-authorities/{id}/revoke`.
  - Revoke a passkey device (revokes its authorities): `DELETE /api/auth/devices/{id}`.
- Readiness/explanation: `GET /api/agents/{id}/state` → `trading_readiness` (presentation only).
  VERIFIED `docs/trading-safety.md:13-24`.

### 11.4 Direct trading routes (sensitive)

| Method | Path | Notes | Evidence |
|---|---|---|---|
| POST | `/api/trading/execute` | owner's direct order `TradeRequest {account_id, operation_id, action, symbol, volume?, price?, stop_loss?, take_profit?, clear_*?, position_id?, order_id?, thesis_id?}` → `TradeResult {operation_id, status, broker_id, code, details}`; used by web Positions/Orders, **not** by the Expo app | VERIFIED `R/trading.py:97-106`, `C/trading.py:14-28,158-163`, `apps/web/src/shell/agent/TradesPage.tsx:88` |
| GET/POST/DELETE | `/api/trading/connections[/{id}]` | broker connections; POST takes `{provider: metaapi\|simulation, account_id, region?, secret_id?, enabled, api_key?}` | VERIFIED `R/trading.py:26-74`, `C/broker.py:8-13` |
| GET | `/api/trading/accounts/{id}` | account snapshot (balances/positions) | VERIFIED `R/trading.py:77-84` |
| POST | `/api/trading/connections/{id}/simulation` | import simulation snapshot | VERIFIED |
| POST | `/api/trading/connections/test` | dry-run broker credential check | VERIFIED `R/connection_tests.py:91-115` |

`AuthorityAction` = `buy, sell, buy_limit, sell_limit, buy_stop, sell_stop, close_position,
modify_position, cancel_order, modify_order`. VERIFIED `C/trading.py:14-25`.

### 11.5 Account authority (signed delegation, passkey step-up)

| Method | Path | Request | Response | Evidence |
|---|---|---|---|---|
| GET | `/api/agents/{id}/account-authorities` | | latest 20 | VERIFIED `R/account_authority.py:21-34` |
| POST | `/api/agents/{id}/account-authorities?permission_revision=` (201) | `AccountAuthorityProposal {thread_id, account_id, management_mode bounded\|full, symbol_scope selected\|account, symbols[], actions[], maximum_* caps, minimum_equity, valid_until (tz), allow_manual_positions}` | pending authority | VERIFIED `R/account_authority.py:37-62`, `C/account_authority.py:41-97` |
| POST | `/api/account-authorities/{id}/challenge` | | `{challenge_id, publicKey: <PublicKeyCredentialRequestOptions>}`; `409 device_registration_required` | VERIFIED `R/account_authority.py:65-73`, `packages/auth/src/lonora_auth/account_authority.py:53-70` |
| POST | `/api/account-authorities/verify` | `DeviceProof {challenge_id, credential}` (passkey assertion, UV required) | active authority | VERIFIED `R/account_authority.py:76-90` |
| POST | `/api/account-authorities/{id}/revoke` | | revoked authority | VERIFIED `R/account_authority.py:93-96` |

Bounded proposals must set every cap and `valid_until`; account scope requires full management.
VERIFIED `C/account_authority.py:58-90`. The Expo client does not call these routes (not in its path
list), only device enrollment. VERIFIED by grep.

---

## 12. Generated UI (lonora-ui v2) in messages

Rendering contract (VERIFIED `docs/genui.md` §1-§8, `T/genui.ts`, `T/genui-catalog.ts`):

- A `ui` part's `document` is a `UiDocument {v: 2, kind, title, sub?, icon, mode?, currency?,
  account_id?, agent_id?, facts, state, calc, blocks[], why?, fallback}`. `kind` ∈ `calculator, form,
  picker, chart, choice, checklist, quiz, timer, diagram, summary`.
- Node types: `Segmented, Select, Number, Slider, Text, Title, Markdown, Note, Badge, KeyValue, Stat,
  Button, Divider, Row, Col, Grid, Card, More, Slot`; server-only row `Delivery`. VERIFIED
  `T/genui-catalog.ts:5-28`. Props per node: `UI_NODE_PROPS` in the same file.
- Expressions (`when`, templates `{expr}`, `@Function(...)`, `@Fact('key')`) must be evaluated exactly
  like `packages/core/src/genui/expr.ts` (shared vectors `tests/fixtures/genui/expr-vectors.json`).
- Actions: `send {intent, data, lock?}`, `go {route ∈ market|tasks|usage|files|agents}`,
  `set {key, value}`, `toggle {key}`, `reset`, `copy {text}`, `open {url}`. Tones `info, good, warn,
  bad, muted, accent`. VERIFIED `T/genui.ts:18-25`, `T/genui-catalog.ts:31-41`.
- `Slot {card, record}` with `card ∈ trade_approval|settle|mandate|secret`: the client draws the **live
  record** (from `/api/trading/approvals` or `/api/owner-actions`) inside a trust frame, with the fixed
  card's own buttons. VERIFIED `docs/genui.md` §4a.
- Streaming: `building: true` while the card streams; `cut: n` when stopped; fail closed on validation
  (`packages/core/src/genui/spec.ts`).

Action submission:

- A Button `send` posts **only** `MessageCreate.ui_submit {source_message_id, part, path, values}` with a
  fresh `client_nonce`; the server reads the intent and data from the stored card, writes the owner
  bubble itself (`origin: "ui_submit"`) and queues a dedicated run. Post immediately, never via the
  offline outbox; retry is the owner's tap. VERIFIED `docs/genui.md` §7, `C/domain.py:85-93`.
- `set/toggle/reset/copy` are client-local; `go` navigates; `open` opens an https URL the compiler
  already allowed.
- "Edit" (unlock) a locking send: `POST /api/threads/{t}/messages/{m}/ui-state/{part}/unlock`.
- Read-time decorations on messages: `ui_lock` (per part), `ui_mark` (`superseded|not_run`), `ui_state`.
  Shared client rules: `packages/core/src/genui/submit.ts`.
- Legacy v1 `VisualDocument` parts (actions `follow_up`, `open_chart`, `open_artifact`) must still render.
  VERIFIED `T/visual-response.ts:64-66`, `docs/genui.md` §9.

---

## 13. Attention, search, usage, capabilities, misc

| Method | Path | Request | Response | Evidence |
|---|---|---|---|---|
| GET | `/api/attention/view` | | `AttentionViewRow[] {kind, id, agent_id, thread_id, group_id?, code?, run_id?, symbol?, summary?, reason?, provider_name?, seen, created_at}` | VERIFIED `R/attention.py:20-24`, `C/attention.py:85-124` |
| GET | `/api/attention` | | `AttentionNotification[]` (pending/ready, unexpired, filtered by policy, latest 50) | VERIFIED `R/attention.py:27-48`, `D/attention.py:72-88` |
| POST | `/api/attention/seen` | `{"notification_id": ""}` | `AttentionNotification` | VERIFIED `R/attention.py:51-56` |
| GET/PUT | `/api/attention/policy` | `{opportunities=true, informational=false, locale: ar\|en}` (locale also selects push language) | same | VERIFIED `C/attention.py:147-150`, `packages/gateway/src/lonora_gateway/push.py:184` |
| GET | `/api/search?q=<= 200&category=chats\|messages\|tasks\|files\|knowledge\|skills&limit=1..100 (32)&offset=0` | | `SearchResponse {q, category, limit, offset, counts, results{category: SearchResult[]}}`; empty `q` = recent feed | VERIFIED `R/search.py:13-25`, `T/search.ts` |
| GET | `/api/usage/summary` | | `{input_tokens, output_tokens, cached_tokens}` | VERIFIED `R/usage.py:27-40` |
| GET | `/api/usage/agents?days=1..366&agent_id=&bucket=day&tz=` | | per-agent usage (+ day buckets) | VERIFIED `R/usage.py:59-91` |
| GET | `/api/usage/series?period=day\|week\|month&agent_id=&tz=` | | `UsageSeries` | VERIFIED `R/usage.py:94-107`, `T/usage.ts` |
| GET | `/api/usage/rank?period=&agent_id=&tz=` | | `UsageRank` | VERIFIED `R/usage.py:110-122` |
| GET | `/api/usage/export.csv?period=&agent_id=&tz=` | | CSV (UTF-8 BOM), attachment | VERIFIED `R/usage.py:125-144` |
| GET | `/api/capabilities` | | `CapabilityReport` | VERIFIED `R/capabilities.py`, `T/capabilities.ts:104` |
| POST/GET/DELETE | `/api/app-opens` | POST `{"timezone": "<IANA>"}` → `{recorded}`; GET/DELETE learned habit | | VERIFIED `R/app_opens.py`, `C/app_opens.py:8-20` |
| GET | `/api/workspace/running` | | running workspace processes | VERIFIED `R/workspace_running.py:23-26` |
| GET | `/api/version` | | `{version, build}` (web build) | VERIFIED `R/version.py` |
| GET | `/health`, `/ready` | | section 3.1 | |

---

## 14. Charts and market data

| Method | Path | Request | Response | Evidence |
|---|---|---|---|---|
| GET | `/api/charts?thread_id=&agent_id=` | | chart `Resource[]` (payload `{account_id, symbol, timeframe, indicators[], annotations[]}`, `state` without `scene`) | VERIFIED `R/charts.py:12`, `M/charts.ts:27-34` |
| POST | `/api/charts` | `ResourceInput` | chart | |
| GET | `/api/charts/{id}/scene` | | `ChartScene {chart_id, revision, scene_version, data_revision?, candle_observed_at?, observation_source?, status: "ready", updated_at, symbol, timeframe, candles[], quote?, indicators[{name, period, series}], annotations[]}` | VERIFIED `R/charts.py:15-21`, `M/charts.ts:35-50` |
| POST | `/api/charts/{id}/refresh` | `{}` | `{"requested": true}`; emits `cloud_charts.refresh_requested` | VERIFIED `R/charts.py:24-39` |
| GET | `/api/market/instruments?account_id=` | | instruments | VERIFIED `R/market.py` |
| GET | `/api/market/symbols?account_id=` | | `string[]` | |
| GET | `/api/market/instrument?account_id=&symbol=` | | instrument | |
| GET | `/api/market/quote?account_id=&symbol=` | | quote | |
| GET | `/api/market/candles?account_id=&symbol=&timeframe=1h&limit=1..1000 (300)` | | candles | |
| GET | `/api/market/calendar` | | economic events (<= 1000, sorted) | |
| WS | `/api/ws/market` | first frame `{"token", "account_id", "symbol"}` within 10 s | stream of quote JSON objects; closes 1008 on error | VERIFIED `W/market.py:17-48` |

Rendering: the Expo app loads `GET {server}/charts/render?locale=ar|en` in a WebView (no cookies) and
posts `{"type":"lonora.chart.scene", scene, account_id, locale}` via `window.postMessage`; the page
answers `lonora.chart.ready/applied/escape`. VERIFIED `apps/mobile/components/chart-renderer.tsx:38-62`.
A Flutter client can reuse this WebView bridge or draw candles natively from `scene.candles`
(the Expo app has a native `CandlestickChart` fallback). VERIFIED same file.

Note `/api/ws/market` reads the cookie **before** the payload token (`W/market.py`, `token =
socket.cookies.get(...) or payload.get("token")`). Harmless for a cookie-less native client.

---

## 15. Push notifications

Provider: **Expo Push Service only**. VERIFIED:

- Registration accepts only Expo tokens `Expo(nent)?PushToken[<8..200 chars>]`.
  `C/push.py:11,16-26`.
- Sending posts to `https://exp.host/--/api/v2/push/send` (optional `LONORA_EXPO_ACCESS_TOKEN`), and
  reads receipts from `getReceipts`. `packages/adapters/src/lonora_adapters/channels/expo_push.py:13-36,60-82`.
- No FCM-direct, WebPush, APNs-direct or UnifiedPush code path exists (grep). VERIFIED.

Registration:

| Method | Path | Request | Response | Errors | Evidence |
|---|---|---|---|---|---|
| PUT | `/api/push/devices/{device_id}` (`^[A-Za-z0-9-]{16,64}$`, random per install) | `{"token": "ExponentPushToken[...]", "platform": "android"\|"ios"}` | `{"registered": true}` | `422` (token format → `invalid_request`), `401` if session revoked/expired at registration | VERIFIED `R/push_devices.py:19-30`, `D/push_devices.py:34-80` |
| DELETE | `/api/push/devices/{device_id}` | | `{"removed": true}` | `404 push_device_not_found` | VERIFIED `R/push_devices.py:33-40` |

Binding: a device row is bound to the registering session; logout deletes it; the token is encrypted
at rest and never returned. A device keeps receiving pushes **after the session expires** until
logout/revocation. VERIFIED `D/push_devices.py:96-123`, `docs/operations.md:638-642`.

Triggers: `attention.ready` events whose code is in `PUSH_CODES`: `approval_required`,
`operation_uncertain`, `secret_requested` (agent-raised), `mandate_proposed` (agent-raised),
`broker_token_rejected`, `broker_account_undeployed`, `broker_connection_lost`,
`broker_rate_limited` (one per account outage), `gateway_stopped`, `model_access_failed`.
VERIFIED `packages/gateway/src/lonora_gateway/push.py:1-28,67-77,125-155`. Messages, replies, Execution
Receipts and incoming calls do **not** push. VERIFIED `docs/operations.md:628`, `docs/GPT_LIVE.md:21`.

Payload (VERIFIED `push.py:177-188`):

```json
{"to": "<expo token>", "title": "<agent name or 'Lonora'>",
 "body": "<fixed catalog text in the owner's attention-policy locale>",
 "data": {"thread_id": "<uuid>", "around": 17},
 "sound": "default", "priority": "high", "channelId": "attention"}
```

`around` (the card's `timeline_seq`) is present only when the card lives in that thread. Tap handling:
open the thread with `GET /api/threads/{id}/messages?around=<seq>`. VERIFIED `M/push.native.ts:67-80`.
No action buttons; a push never approves anything. Delivery: at most once per record per device;
unknown outcomes never resent; DeviceNotRegistered receipts remove the device. VERIFIED
`docs/operations.md:628-636`.

What a Flutter client must do (INFERRED):

1. Create an Android notification channel with id **`attention`** (high importance).
2. Obtain an **Expo push token**. Options: (a) embed Expo's native `expo-notifications` module in the
   Flutter app (heavy), or (b) get an FCM registration token via `firebase_messaging` and exchange it
   at Expo's `https://exp.host/--/api/v2/push/getExpoPushToken` endpoint with `type: "fcm"`,
   `deviceToken`, `projectId` (`LONORA_EXPO_PROJECT_ID`), `appId` (the Android package), `deviceId`,
   `development: false`. UNKNOWN whether the owner's Expo project accepts a new `appId`; Expo must hold
   FCM V1 credentials for the Firebase project that contains the new package (`docs/operations.md:650-656`
   documents this only for `ai.lonora.mobile`).
3. `PUT /api/push/devices/{install-id}` after every login and on token rotation; `DELETE` when the user
   disables notifications.
4. Expo delivers FCM **notification** messages (title/body shown by the system while backgrounded),
   with `data` available on tap. INFERRED (Expo service behaviour, not in repo).

A backend change to accept raw FCM tokens would be the cleaner path for a non-Expo app; nothing in the
repository supports it today. VERIFIED (absence).

---

## 16. Mobile updates and APK distribution

`/api/mobile/updates` (VERIFIED `R/mobile_updates.py:1-146`, `docs/mobile/ota.md`):

- Implements **Expo Updates protocol v1** for the Expo/React Native app: requires headers
  `expo-protocol-version: 1`, `expo-platform: android|ios`, `expo-channel-name: preview|production`,
  `expo-runtime-version: <40..64 hex fingerprint>`; else `400 mobile_update_request_invalid`.
- Returns a signed `application/expo+json` manifest (`expo-signature`, RSA, keyid `main`), a signed
  multipart `rollBackToEmbedded` directive, or 204 (no update / unknown runtime). Rollout cohorts via
  `expo-extra-params: lonora-client="<uuid>"`. Assets at `/api/mobile/updates/assets/<sha256>.<ext>`.
- Payloads are JavaScript bundles and assets for runtime fingerprints of the Expo app. **Useless to a
  Flutter app.** INFERRED (content is a Metro bundle, `docs/mobile/ota.md:15`).

APK: `GET|HEAD /download/lonora.apk` serves one file (`LONORA_ANDROID_APK_PATH`), public, `no-cache`,
validated ZIP magic, with ETag/Last-Modified (Starlette FileResponse). VERIFIED `A/app.py:135-151`,
`A/env.py:87`. There is **no** version-metadata endpoint for native builds (`/api/version` reports the
web build only, VERIFIED `R/version.py`). A self-updating Flutter app could compare `ETag`/
`Last-Modified`/`Content-Length` from `HEAD /download/lonora.apk`, but that file is the Expo app today.
INFERRED.

Package assumptions (`ai.lonora.mobile`):

| Place | Value | Evidence |
|---|---|---|
| Expo app `android.package` | `brand.applicationId` = `ai.lonora.mobile` | VERIFIED `apps/mobile/app.config.ts:45`, `packages/ui-tokens/src/brand.ts:5` |
| Passkey assetlinks package | `LONORA_PASSKEY_ANDROID_PACKAGE`, default `ai.lonora.mobile`, single value | VERIFIED `A/env.py:22`, `A/device_metadata.py:28` |
| Firebase/Expo push setup docs | Android app `ai.lonora.mobile` | VERIFIED `docs/operations.md:653` |
| OTA default URL | `https://lonora.lork.cloud/api/mobile/updates` | VERIFIED `apps/mobile/app.config.ts:5` |
| API (REST/WS) | no package or client check at all | VERIFIED (`require_owner` only) |

Would `ai.lonora.android` be supported? REST/WebSocket: yes, unchanged. Passkeys: only after the
operator changes `LONORA_PASSKEY_ANDROID_PACKAGE` (exclusive) and adds the new signing fingerprint, or
after a backend change to list two packages. Push: only if an Expo token can be minted for the new
`appId` in the owner's Expo project with FCM credentials (UNKNOWN), or after a backend FCM change. OTA:
not applicable. APK download: would need the operator to replace the served file or a new route.

---

## 17. Voice (GPT-Live WebRTC) and incoming calls

### 17.1 Voice call signalling

| Method | Path | Request | Response | Errors | Evidence |
|---|---|---|---|---|---|
| GET | `/api/voice/status` | | `{"transport": "gpt_live", "transport_configured": bool (OpenAI key present), "model": "gpt-live-1..."}` | | VERIFIED `R/voice.py:68-75` |
| POST | `/api/voice/sessions` (201) | `VoiceSessionCreate {agent_id, thread_id, mode: "gpt_live", sdp (offer, 1..65536), client_nonce 1..80, incoming_call_id?}` | `{"session_id", "sdp": "<answer>"}` (returned only after the Gateway attached) | `409 voice_session_closed`, `409 voice_agent_thread_mismatch`, `409 agent_paused`, `409 voice_session_mismatch`, `502 voice_connection_failed`, `503 voice_backend_unavailable` | VERIFIED `R/voice.py:24-30`, `C/voice.py:8-16`, `packages/voice/src/lonora_voice/sessions.py:103-224` |
| GET | `/api/voice/sessions/{id}` | | `{session_id, status, model, error, input[], output[], usage, finalized}` | | VERIFIED `sessions.py:277-289` |
| DELETE | `/api/voice/sessions/{id}` | | `{"closed": true}` | | VERIFIED `R/voice.py:33-38` |
| POST | `/api/voice/cancel-initialization` | `{"client_nonce"}` | `{"cancelled": true}` (abandon before a session id exists) | | VERIFIED `R/voice.py:85-90` |
| POST | `/api/voice/sessions/{id}/transcript` (202) | `{text 1..30000, client_nonce, final=true}` | commit result; `409 voice_session_closed` | | VERIFIED `R/voice.py:41-52`, `C/voice.py:19-22` |
| POST | `/api/voice/sessions/{id}/interrupt` | `{}` | `{"cancelled": [run ids]}` (barge-in) | | VERIFIED `R/voice.py:55-65` |
| WS | `/api/ws/voice` | first frame `{token, session_id}`; then `{"type":"interrupt"}` or `{"transcript": {...}}`; each answered with a JSON result | | | VERIFIED `W/voice.py:19-71` (not used by the Expo app) |

What a native client must do (VERIFIED `M/voice-transport.ts:47-238`, `M/voice-device.native.ts:5-56`):

1. Request `RECORD_AUDIO`; start in-call audio routing (speakerphone on).
2. `new RTCPeerConnection({})` (no ICE servers configured by the client); add the microphone track;
   create the data channel **`oai-events`** before the offer.
3. `createOffer` → `setLocalDescription` → **wait for ICE gathering complete** (10 s timeout); the
   server needs a full non-trickle SDP.
4. `POST /api/voice/sessions` with the SDP and a stable `client_nonce` (+ `incoming_call_id` when
   answering an incoming call). Set the returned SDP as the remote answer.
5. Data channel events: `session.started` (connected), `session.output_audio.delta` /
   `session.output_transcript.delta` (agent speaking), `error`, `session.closed` (finalized).
6. To end: send `{"type":"session.close"}` on the data channel, wait up to 2.5 s for
   `session.closed`, then `DELETE /api/voice/sessions/{id}`; if no session id yet,
   `POST /api/voice/cancel-initialization {client_nonce}`. Close the peer.
7. Treat peer `disconnected|failed|closed` as `voice_connection_failed`.

Media flows directly between the device and the OpenAI Live API; the project key stays on the server;
"There is no separate RTC server or public RTC port". VERIFIED `docs/GPT_LIVE.md:5-7` (the media
endpoint being OpenAI is INFERRED from the `oai-events` channel and the doc).

### 17.2 Incoming calls (agent rings the owner)

| Method | Path | Request | Response | Evidence |
|---|---|---|---|---|
| GET/PUT | `/api/voice/incoming/policy` | `IncomingCallPolicy {channel: notify\|message\|call, enabled (derived), device_id (an enrolled **passkey device id**, required for call), opportunities, action_required, critical, timezone, quiet_start/end_hour 0..23, quiet_start/end_minute 0..1439, ttl_seconds 15..120 (45), minimum_interval_seconds 60..86400 (300)}` | same | VERIFIED `R/incoming_calls.py:24-36`, `C/incoming_calls.py:41-103` |
| GET | `/api/voice/incoming` | | ringing invitations (<= 20) | VERIFIED `R/incoming_calls.py:39-56` |
| POST | `/api/voice/incoming/{id}/respond` | `{action: accept\|reject\|cancel, device_id}` | `call_data`; `403 incoming_call_device_mismatch`, `403 incoming_call_device_unavailable`, `404 incoming_call_not_found` | VERIFIED `R/incoming_calls.py:59-69`, `C/incoming_calls.py:134-136`, `packages/voice/src/lonora_voice/incoming.py:283-300` |

Call record: `{id, agent_id, thread_id, status: ringing|accepted|rejected|missed|cancelled, reason,
attention_id, expires_at, version, execution_authorized: false}`. Discovery is in-app only: the
`voice.incoming.updated` event or polling `GET /api/voice/incoming`. **No push wakes the phone for a
call** (`state.delivery = "provider_unconfigured"`, VERIFIED `incoming.py:258`; "native push-initiated
incoming calls are not yet implemented", VERIFIED `docs/GPT_LIVE.md:21`). After `accept`, join with
`POST /api/voice/sessions` and `incoming_call_id`. An accepted call never authorizes trading.

---

## 18. Settings: providers, model router, integrations, connections

| Method | Path | Request | Response / notes | Evidence |
|---|---|---|---|---|
| GET | `/api/providers` | | `[{id, configured, sign_in?: {signed_in, ...}}]` (no secret) | VERIFIED `R/providers.py:25-48` |
| PUT | `/api/providers/{provider}/credential` | `{"api_key": 8..4096}` | `{"configured": true}`; ChatGPT → `409 chatgpt_sign_in_required`; owner endpoint → `404 provider_not_supported` | VERIFIED `R/providers.py:51-64`, `C/model_catalog.py:18-19` |
| GET | `/api/providers/{provider}/models` | | Lonora's catalog `ModelDescriptor[]` | VERIFIED `R/providers.py:67-76` |
| POST | `/api/providers/{provider}/test` | `{"api_key"}` | `{"ok": true}` or `504 connection_test_timeout` (stores nothing) | VERIFIED `R/connection_tests.py:46-58` |
| POST | `/api/providers/openai_chatgpt/sign-out` | | sign-out result | VERIFIED `R/chatgpt_sign_in.py:161-167` |
| GET/PUT | `/api/settings/models` | `RoutingPolicy {mode: unified\|custom, unified?: {provider, model}, routes: {capability: {provider, model}}}` | same | VERIFIED `R/model_router.py:29-39`, `C/model_routing.py:13-60` |
| PUT | `/api/settings/models/backups` | `{"choices": [<= 3 ModelSelection]}` | same | VERIFIED `R/model_router.py:43-50`, `C/model_backups.py:7-8` |
| GET/PUT | `/api/settings/models/context` | `ModelContextPolicy` | same | VERIFIED `R/model_router.py:53-69` |
| CRUD | `/api/integrations` | `Integration` (types `brave_search, economic_calendar, news_feed, telegram, webhook`) | resources | VERIFIED `R/integrations.py:71`, `C/integrations.py:17` |
| POST | `/api/integrations/secrets` (201) | `{name 1..80, value 1..16000}` | `{"id"}` (write-only) | VERIFIED `R/integrations.py:74-83` |
| CRUD | `/api/mcp` | `McpConnection` | resources; delete revokes trust | VERIFIED `R/mcp.py` |
| POST | `/api/mcp/test` | `{url https 8..2048, token?}` | `{ok, tools[], writes, blocked, unsupported}` | VERIFIED `R/connection_tests.py:67-88` |
| GET/POST | `/api/trusted-sources` | `{kind: github\|github_owner\|github_repo\|feed_domain, identifier}` | sources | VERIFIED `R/trusted_sources.py:52-65`, `C/trusted_sources.py:55-66` |
| POST | `/api/trusted-sources/{id}/revoke`, `/restore` | | source | VERIFIED |
| POST | `/api/trusted-sources/mcp/{connection_id}/preview` | | `{id, digest, tools...}` | VERIFIED `R/trusted_sources.py:111-132` |
| POST | `/api/trusted-sources/mcp/{connection_id}` | `{tier: read\|write_nonfinancial, digest sha256}` | trusted source; `409 mcp_tools_changed` | VERIFIED `R/trusted_sources.py:135-171`, `C/trusted_sources.py:68-72` |
| GET | `/api/secrets` | | `[{id, name, updated_at}]` (names only) | VERIFIED `R/agent_secrets.py:10-17`, `D/secrets.py:50` |
| DELETE | `/api/secrets/{id}` | | `{"deleted": true}`; refused if in use | VERIFIED `R/agent_secrets.py:20-28` |

Provider ids: `openai, openai_chatgpt, anthropic, deepseek, zai, openrouter, openai_compatible`.
VERIFIED `C/model_routing.py:13-15`. The Expo app reads `/providers`, `/settings/models`, deletes
integrations and manages trusted sources but does not post provider keys (not in its path list).

---

## 19. Safety guidance for a mobile client

### 19.1 Never exposed by the server (good) and must never be exposed by the client

- No route returns secret values: provider keys, integration secrets, broker passwords/tokens,
  secret-card values and push tokens are write-only; listings return names/ids. VERIFIED
  (`R/agent_secrets.py:10-17`, `R/secret_cards.py` docstring, `R/push_devices.py:1-2`).
- The bearer token is the only credential. Store it in Android Keystore-backed storage
  (flutter_secure_storage / EncryptedSharedPreferences), as the Expo app uses SecureStore
  (VERIFIED `M/storage.ts:25-33`). Never put it in URLs, logs, crash reports or WebViews (the chart
  WebView is deliberately cookie-less, VERIFIED `chart-renderer.tsx:107-112`).
- Do not log `client_nonce`, message text or tokens (the server hashes the nonce in logs, VERIFIED
  `R/messages.py:104-114`).
- The bootstrap (setup) token from a deep link is held in memory only and only for its server
  (VERIFIED `M/connect-link.ts:52-62`).

### 19.2 Routes a mobile client should use (the Expo app's set, VERIFIED by grep)

Auth/session, onboarding, push devices, app-opens, agents (+state, model, model/summary, memory,
skills, notifications, conversation), threads (+inbox, prefs, settings, read, clear, options,
collaboration), messages (+reactions, unlock), runs (list, cancel, resume, retry), artifacts (upload,
list, get, file), groups, chat lists, routines, tasks (+control), watches control, attention
(+view, seen), owner-actions (list, mandate, decision, renew, secret, chatgpt), trading approvals
(list, decision), trading receipts, trading connections (read), market symbols, charts (+scene,
refresh), peer-messages, capabilities, providers (read), settings/models (read), integrations
(delete), trusted sources (revoke/restore/MCP trust), owner profile/preferences/lines, usage summary,
voice (status, sessions, cancel-initialization), incoming calls (+policy, respond), device enrollment,
workspace running (+stop, stop-all), `/ws/events`.

### 19.3 Routes to keep out of the mobile client (or gate heavily)

| Route | Why | Evidence |
|---|---|---|
| POST `/api/trading/execute` | direct broker order outside the agent/approval path; Expo app never calls it | `R/trading.py:97-106` |
| POST/DELETE `/api/trading/connections`, POST `/simulation` | broker credentials / account removal | `R/trading.py:47-94` |
| POST `/api/runs` | low-level run creation with arbitrary `trigger`/`metadata` | `R/runs.py:46-51` |
| POST `/api/webhook` | server-to-server HMAC | `R/webhook.py` |
| PUT `/api/providers/*/credential`, POST `/api/integrations/secrets`, POST `/api/*/test` | typing secrets into a phone; web does it; acceptable only with care | `R/providers.py`, `R/integrations.py`, `R/connection_tests.py` |
| PUT `/api/settings/models*` | global routing affects all agents | `R/model_router.py` |
| Generic POST/PUT on `/api/artifacts`, `/api/skills`, `/api/mcp`, `/api/integrations`, `/api/tickets` | free-form payloads | section 3.3 |
| Account-authority proposal/verify | signs live trading delegation; needs passkey parity with the web flow | `R/account_authority.py` |

### 19.4 Safety invariants the client must respect

- A push, a generated card, a voice utterance or an incoming call never approves, settles or switches
  a mode; only the fixed cards with the owner session do. VERIFIED `docs/genui.md` intro and §4a,
  `push.py:17-21`, `C/incoming_calls.py:1`.
- Never retry a trade-related action with a new identity; reuse `operation_id`; never auto-resend
  card submits, input answers or edits. VERIFIED `docs/trading-safety.md`, `docs/genui.md` §7.
- Draw fixed cards (approval, settle, mandate, secret) from the live record and refetch after any
  `409` (already decided). VERIFIED `docs/genui.md` §4a "Fallback row".

---

## 20. Gaps, unknowns and backend changes a new Android client may need

| Item | Status |
|---|---|
| Session lifetime 24 h default, no refresh token | VERIFIED; operator can raise to 30 days; otherwise re-login daily |
| No "list/revoke other sessions" | VERIFIED absent |
| Push requires Expo tokens; no FCM direct | VERIFIED; Flutter must mint an Expo token (UNKNOWN feasibility for a new package) or backend must add FCM |
| Passkeys bound to one Android package | VERIFIED; config change or backend change for `ai.lonora.android` |
| OTA is Expo-only; no native version endpoint | VERIFIED; Flutter self-update needs a new endpoint or uses Play/side-load |
| Incoming calls cannot wake the phone | VERIFIED; in-app only |
| Event payloads for many kinds not formally specified | UNKNOWN; treat as invalidation signals |
| Rate-limit key behind Caddy | INFERRED shared bucket |
| Event retention unbounded; replay from 0 without `live` is expensive | INFERRED |
| WebSocket Origin must be absent or equal to `LONORA_ALLOWED_ORIGIN` | VERIFIED |
| Validation errors collapse to `invalid_request` | VERIFIED; map client-side checks to friendly text before sending |
| Maintenance 503 body uses `error`, not `code` | VERIFIED |

## 21. Appendix: frequently seen error codes

`unauthorized` 401, `csrf_required` 403, `rate_limited` 429, `request_body_too_large` 413,
`invalid_request` 422, `resource_conflict` 409, `endpoint_not_found` 404, `request_failed`,
`thread_not_found`, `agent_not_found`, `run_not_found`, `message_not_found`, `artifact_not_found`,
`<kind>_not_found` (resources, e.g. `artifacts_not_found`, `groups_not_found`), `version_conflict`,
`agent_paused`, `input_answer_expired`, `input_answer_invalid`, `input_answer_conflict`,
`ui_submit_conflict`, `reply_not_found`, `voice_artifact_invalid`, `message_command_invalid`,
`attachment_too_large`, `invalid_filename`, `artifact_file_missing`, `artifact_not_text`,
`run_cannot_resume`, `run_not_retryable`, `run_retry_too_early` (+`retry_after_seconds`),
`task_resume_required`, `task_use_control`, `thread_pin_limit`, `owner_action_*`,
`trade_approval_expired`, `chatgpt_sign_in_required`, `device_*`, `incoming_call_*`,
`voice_session_closed`, `voice_backend_unavailable`, `voice_connection_failed`,
`push_device_not_found`, `event_cursor_invalid`, `websocket_auth_invalid`, `websocket_cursor_invalid`,
`mobile_update_request_invalid`, `android_release_unavailable`, `invalid_bootstrap_token`,
`owner_already_initialized`, `invalid_email`, `invalid_password`, `database_unavailable`.
Shared client error texts (Arabic/English) live in `packages/core` (`agentPermissionError`,
`financialBoundaryError`, `ownerActionError`, `ownerProfileError`) and `M/i18n.ts`. VERIFIED
`M/session.tsx` `errorText`.
